// Nine digits starting with 9 identify a local Peruvian mobile number.
// Explicit international prefixes are preserved; ambiguous local numbers are rejected.
export function normalizePhone(value){
  const raw=String(value||'').trim();
  if(!/^(?:\+|00)?[0-9 ()-]+$/.test(raw))return null;
  let digits=raw.replace(/[^0-9]/g,'');
  const explicit=raw.startsWith('+')||raw.startsWith('00');
  if(raw.startsWith('00'))digits=digits.slice(2);
  if(!explicit&&/^9[0-9]{8}$/.test(digits))digits='51'+digits;
  else if(!explicit&&digits.length<10)return null;
  if(!/^[1-9][0-9]{6,14}$/.test(digits))return null;
  return {tel:`+${digits}`,whatsapp:digits};
}
