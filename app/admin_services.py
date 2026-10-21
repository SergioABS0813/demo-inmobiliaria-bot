from io import BytesIO
import logging
import re
from urllib.parse import urlsplit, unquote
from uuid import uuid4
import warnings
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from .config import get_settings

BUCKET = 'imagenes-inmobiliaria-demo'
MAX_FILE = 8 * 1024 * 1024
MAX_BATCH = 24 * 1024 * 1024
MAX_PIXELS = 24_000_000
FORMATS = {'JPEG':('jpg','image/jpeg'),'PNG':('png','image/png'),'WEBP':('webp','image/webp')}
ADMIN_FIELDS = 'id,titulo,descripcion,tipo_operacion,tipo_inmueble,condicion,proyecto,distrito_id,moneda,precio,cantidad_dormitorios,cantidad_banos,cocheras,area_total,direccion,disponible,agente_id,created_at,distritos(nombre),agentes(nombre)'
log = logging.getLogger(__name__)


def read_all(db,table,fields):
    rows=[]
    while True:
        batch=db.table(table).select(fields).order('id').range(len(rows),len(rows)+499).execute().data
        rows.extend(batch)
        if len(batch)<500:return rows


def get_property(db, property_id):
    rows=db.table('propiedades').select(ADMIN_FIELDS).eq('id',property_id).limit(1).execute().data
    if not rows:raise HTTPException(404,'La propiedad no existe.')
    return rows[0]


def save_property(db,body,property_id=None):
    data=body.model_dump(mode='json',exclude_unset=True)
    if property_id is not None:get_property(db,property_id)
    for field,table in (('distrito_id','distritos'),('agente_id','agentes')):
        if data.get(field) is not None:
            rows=db.table(table).select('id').eq('id',data[field]).limit(1).execute().data
            if not rows:raise HTTPException(422,'El distrito o agente seleccionado ya no existe.')
    if property_id is None:
        data.setdefault('disponible',False)
        rows=db.table('propiedades').insert(data).execute().data
    else:
        if not data:return get_property(db,property_id)
        rows=db.table('propiedades').update(data).eq('id',property_id).execute().data
    if not rows:raise HTTPException(409,'No se guardaron los cambios. Recarga la propiedad.')
    # Property-only writes never replace/delete image rows.
    return get_property(db,rows[0]['id'])


def validate_image(data,content_type):
    if not data or len(data)>MAX_FILE:raise HTTPException(422,'Cada imagen debe tener entre 1 byte y 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                fmt=image.format
                if fmt not in FORMATS:raise ValueError()
                if image.width*image.height>MAX_PIXELS or getattr(image,'is_animated',False):raise ValueError()
                image.verify()
            with Image.open(BytesIO(data)) as image:image.load()
    except (UnidentifiedImageError,OSError,ValueError,SyntaxError,OverflowError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(422,'Imagen inválida. Usa JPEG, PNG o WebP estático de hasta 24 megapíxeles.')
    extension,mime=FORMATS[fmt]
    if content_type not in (None,'application/octet-stream',mime):
        raise HTTPException(422,'El contenido de la imagen no coincide con su formato declarado.')
    return extension,mime


def storage_key(property_id,category,filename,extension):
    if category not in ('vista_1','vista_2','plano'):raise HTTPException(422,'Categoría no válida.')
    stem=re.sub(r'[^a-zA-Z0-9_-]+','-',str(filename or 'foto').rsplit('.',1)[0]).strip('-')[:35] or 'foto'
    return f'propiedad_{property_id}/{category}/{uuid4().hex}-{stem}.{extension}'


def owned_storage_key(url,property_id):
    """Never delete arbitrary remote URLs or a different property's objects."""
    if not url:return None
    actual=urlsplit(url); expected=urlsplit(get_settings().supabase_url)
    prefix=f'/storage/v1/object/public/{BUCKET}/'
    if actual.scheme!='https' or actual.netloc!=expected.netloc or not actual.path.startswith(prefix):return None
    key=unquote(actual.path[len(prefix):])
    parts=key.split('/')
    if len(parts)!=3 or parts[0]!=f'propiedad_{property_id}' or parts[1] not in ('vista_1','vista_2','plano'):return None
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.(jpg|jpeg|png|webp)',parts[2],re.I) or '..' in parts[2]:return None
    return key


def defer_cleanup(db,key):
    try:
        db.table('propiedad_archivos_pendientes').upsert({'bucket':BUCKET,'object_key':key},on_conflict='bucket,object_key').execute()
        return True
    except Exception:
        # The key is admin-generated and contains no access tokens/credentials.
        log.error('No se pudo registrar limpieza pendiente de Storage: %s',key)
        return False


def upload_one(db,property_id,category,filename,data,extension,mime):
    key=storage_key(property_id,category,filename,extension)
    bucket=db.storage.from_(BUCKET)
    try:bucket.upload(key,data,{'content-type':mime,'upsert':'false'})
    except Exception:
        # A transport timeout can occur after Storage accepted the bytes.
        defer_cleanup(db,key)
        return None,{'archivo':filename,'mensaje':'No se pudo confirmar la subida. Revisa las imágenes antes de reintentar.'}
    try:
        url=bucket.get_public_url(key)
        row=db.rpc('ru_admin_registrar_imagen',{'p_propiedad_id':property_id,'p_url':url,'p_categoria':category}).execute().data
        return row,None
    except Exception:
        # Storage and PostgreSQL cannot share one transaction: compensate.
        pending=False
        try:bucket.remove([key])
        except Exception:
            pending=True
            tracked=defer_cleanup(db,key)
            if not tracked:
                return None,{'archivo':filename,'mensaje':'No se registró la foto y falló su limpieza. Conserva esta ruta para revisión manual.','ruta_pendiente':key}
        return None,{'archivo':filename,'mensaje':'No se pudo registrar la fotografía.'+(' Su archivo quedó pendiente de limpieza.' if pending else ' Se retiró el archivo subido.')}


def run_cleanup(db,limit=20):
    pending=db.table('propiedad_archivos_pendientes').select('id,bucket,object_key').order('id').limit(limit).execute().data
    cleaned=0
    for row in pending:
        # Queued paths originate only in privileged server-side operations.
        if row['bucket']!=BUCKET:continue
        try:
            db.storage.from_(row['bucket']).remove([row['object_key']])
            db.table('propiedad_archivos_pendientes').delete().eq('id',row['id']).execute()
            cleaned+=1
        except Exception:
            # Keep the durable queue row for a later explicit retry.
            continue
    return {'eliminados':cleaned,'pendientes_revisados':len(pending)-cleaned}
