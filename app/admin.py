from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from .db import get_db
from .admin_auth import require_admin, require_admin_write
from .admin_schemas import PropertyWrite, AvailabilityIn, ImageOrderIn, Category
from . import admin_services as service

router=APIRouter(tags=['Administración'],dependencies=[Depends(require_admin)])
Write=Depends(require_admin_write)


@router.get('/agente/propiedades',include_in_schema=False)
def panel():
    return FileResponse(Path(__file__).parent/'templates'/'agente_propiedades.html')


@router.get('/api/agente/opciones')
def options(db=Depends(get_db)):
    districts=service.read_all(db,'distritos','id,nombre,activo')
    agents=service.read_all(db,'agentes','id,nombre')
    return {'distritos':sorted(districts,key=lambda d:(not d['activo'],d['nombre'].casefold())),
            'agentes':sorted(agents,key=lambda a:(a['nombre'] or '').casefold())}


@router.get('/api/agente/propiedades')
def listing(q:str=Query('',max_length=200),distrito_id:int|None=Query(None,gt=0),disponible:bool|None=None,
            offset:int=Query(0,ge=0),limit:int=Query(25,ge=1,le=100),db=Depends(get_db)):
    query=db.table('propiedades').select(service.ADMIN_FIELDS,count='exact')
    if q.strip():
        escaped=q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        query=query.ilike('titulo','%'+escaped+'%')
    if distrito_id is not None:query=query.eq('distrito_id',distrito_id)
    if disponible is True:query=query.eq('disponible',True)
    if disponible is False:query=query.or_('disponible.eq.false,disponible.is.null')
    result=query.order('id',desc=True).range(offset,offset+limit-1).execute()
    return {'propiedades':result.data,'total':result.count}


@router.post('/api/agente/propiedades',status_code=201,dependencies=[Write])
def create(body:PropertyWrite,db=Depends(get_db)):
    return service.save_property(db,body)


@router.get('/api/agente/propiedades/{property_id}')
def detail(property_id:int,db=Depends(get_db)):
    return service.get_property(db,property_id)


@router.patch('/api/agente/propiedades/{property_id}',dependencies=[Write])
def update(property_id:int,body:PropertyWrite,db=Depends(get_db)):
    return service.save_property(db,body,property_id)


@router.patch('/api/agente/propiedades/{property_id}/disponibilidad',dependencies=[Write])
def availability(property_id:int,body:AvailabilityIn,db=Depends(get_db)):
    return service.save_property(db,PropertyWrite(disponible=body.disponible),property_id)


@router.get('/api/agente/propiedades/{property_id}/imagenes')
def images(property_id:int,db=Depends(get_db)):
    service.get_property(db,property_id)
    return db.table('propiedad_imagenes').select('id,propiedad_id,url,orden,categoria').eq('propiedad_id',property_id).order('orden',nullsfirst=False).order('id').execute().data


@router.post('/api/agente/propiedades/{property_id}/imagenes',dependencies=[Write])
async def upload(property_id:int,categoria:Annotated[Category,Form()],files:Annotated[list[UploadFile],File()],db=Depends(get_db)):
    await run_in_threadpool(service.get_property,db,property_id)
    if not 1<=len(files)<=6:raise HTTPException(422,'Selecciona entre 1 y 6 imágenes por subida.')
    prepared=[];size=0
    try:
        for file in files:
            data=await file.read(service.MAX_FILE+1);size+=len(data)
            if size>service.MAX_BATCH:raise HTTPException(422,'La suma de imágenes no debe superar 24 MB.')
            extension,mime=await run_in_threadpool(service.validate_image,data,file.content_type)
            prepared.append((file.filename or 'foto',data,extension,mime))
    finally:
        for file in files:await file.close()
    # Validate the whole selection before starting Storage writes.
    uploaded=[];errors=[]
    for name,data,extension,mime in prepared:
        row,error=await run_in_threadpool(service.upload_one,db,property_id,categoria,name,data,extension,mime)
        if row:uploaded.append(row)
        if error:errors.append(error)
    return {'imagenes':uploaded,'errores':errors}


@router.put('/api/agente/propiedades/{property_id}/imagenes/orden',dependencies=[Write])
def reorder(property_id:int,body:ImageOrderIn,db=Depends(get_db)):
    return db.rpc('ru_admin_ordenar_imagenes',{'p_propiedad_id':property_id,'p_ids':body.ids}).execute().data


@router.delete('/api/agente/propiedades/{property_id}/imagenes/{image_id}',dependencies=[Write])
def remove_image(property_id:int,image_id:int,db=Depends(get_db)):
    service.get_property(db,property_id)
    rows=db.table('propiedad_imagenes').select('id,url').eq('id',image_id).eq('propiedad_id',property_id).limit(1).execute().data
    if not rows:raise HTTPException(404,'La imagen ya no existe. Recarga la lista.')
    row=rows[0];key=service.owned_storage_key(row['url'],property_id)
    db.rpc('ru_admin_retirar_imagen',{'p_propiedad_id':property_id,'p_imagen_id':image_id,'p_url_esperada':row['url'],
        'p_bucket':service.BUCKET if key else None,'p_object_key':key}).execute()
    result=service.run_cleanup(db)
    return {'eliminada':True,'archivo_externo_conservado':key is None,**result}


@router.get('/api/agente/archivos-pendientes')
def pending(db=Depends(get_db)):
    result=db.table('propiedad_archivos_pendientes').select('id',count='exact').limit(1).execute()
    return {'total':result.count}


@router.post('/api/agente/archivos-pendientes/reintentar',dependencies=[Write])
def cleanup(db=Depends(get_db)):
    return service.run_cleanup(db)
