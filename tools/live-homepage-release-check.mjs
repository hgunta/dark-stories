// Check live Render preview page without changing any user data.
const base='https://dark-stories-preview.onrender.com';
for(const path of ['/', '/?release_probe=pr41']) {
  const response=await fetch(base+path,{headers:{'Cache-Control':'no-cache'},signal:AbortSignal.timeout(90000)});
  const html=await response.text();
  const status={
    path,
    http:response.status,
    title:html.match(/<title>([^<]*)<\/title>/i)?.[1]||'',
    hasNewBrand:html.includes('CRACK THE CASE'),
    hasOldBrand:html.includes('DARK STORIES'),
    hasNewPixelFolder:html.includes('viewBox="0 0 96 72"'),
    hasRandomFeatured:html.includes('crack-the-case-last-featured'),
    hasNewOptIn:html.includes('Share future chat to improve the moderator'),
    hasOldExpandDetails:html.includes('id="playtest-sharing-details"'),
    contentLength:html.length,
    renderCache:response.headers.get('x-render-cache')||'',
    etag:response.headers.get('etag')||'',
  };
  console.log('LIVE_PREVIEW_STATE '+JSON.stringify(status));
}
