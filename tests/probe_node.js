require('https').get('https://api.ipify.org', r => {
  let d=''; r.on('data',c=>d+=c); r.on('end',()=>console.log('NODE_SAW:'+d));
}).on('error', e => console.log('NODE_ERR:'+e.message));
