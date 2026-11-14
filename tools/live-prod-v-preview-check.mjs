// Read-only live release comparison. Do not print player data or credentials.
const targets = {
  production: 'https://dark-stories-8frx.onrender.com',
  preview: 'https://dark-stories-preview.onrender.com'
};
for (const [name, origin] of Object.entries(targets)) {
  for (const path of ['/', '/api/mysteries']) {
    try {
      const res=await fetch(origin+path,{signal:AbortSignal.timeout(100000),headers:{'Cache-Control':'no-cache'}});
      const body=await res.text();
      const out={site:name,path,status:res.status,finalUrl:res.url,
        title:body.match(/<title>([^<]+)<\\/title>/i)?.[1] ?? null,
        newBrand:body.includes('CRACK THE CASE'),
        oldBrand:body.includes('DARK STORIES'),
        randomized:body.includes('crack-the-case-last-featured'),
        newFolder:body.includes('viewBox="0 0 96 72"'),
        size:body.length,
        cacheControl:res.headers.get('cache-control'),
        etag:res.headers.get('etag')};
      if(path.includes('mysteries')) {
        try {const cases=JSON.parse(body);out.isArray=Array.isArray(cases);
          out.case3=cases.find?.(c=>c.id==='ms-003')?.title??null;
          out.caseCount=cases.length;
        }catch {out.responseSnippet=body.slice(0,100)}
      }
      console.log('DEPLOY_CHECK '+JSON.stringify(out));
    }catch(err){console.log('DEPLOY_CHECK '+JSON.stringify({site:name,path,error:String(err)}))}
  }
}
