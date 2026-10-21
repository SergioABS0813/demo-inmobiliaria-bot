// Run with: node --experimental-default-type=module tests/agent_phone.test.mjs
import assert from 'node:assert/strict';
import {normalizePhone} from '../static/js/agent-phone.js';

for(const [input,expected] of [
  ['999 999 999','51999999999'],
  ['+51 999 999 999','51999999999'],
  ['+1 (202) 555-0123','12025550123'],
  ['0012025550123','12025550123'],
  ['34600111222','34600111222'],
  ['',null],['username_meta',null],['12345',null],['123456789',null],['+000000000',null]
]){
  const result=normalizePhone(input);
  assert.equal(result?.whatsapp??null,expected,input);
  if(result)assert.equal(result.tel,`+${expected}`);
}
console.log('10 phone normalization cases passed.');
