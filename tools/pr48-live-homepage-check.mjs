// Read-only smoke test of the actual production webpage after PR #48.
const base='https://dark-stories-8frx.onrender.com';
const response=await fetch(base+'/?pr48_verify=8153e72',{headers:{'Cache-Control':'no-cache'},signal:AbortSignal.timeout(90000)});
const html=await response.text();
const hero=html.match(/<div class="hero">([\s\S]*?)<\/div>/i)?.[1]??'';
const result={
  http:response.status,
  title:html.match(/<title>([^<]*)<\/title>/i)?.[1]??null,
  hasHeading:hero.includes('Every story has a secret.'),
  hasInstructions:hero.includes('Ask yes-or-no questions'),
  hasBetaBanner:hero.includes('Public beta') || hero.includes('class="beta-note"'),
  consentPreserved:html.includes('id="playtest-opt-in"')&&html.includes('Share future chat to improve the moderator'),
  newBrand:html.includes('CRACK THE CASE')
};
const passed=response.ok&&result.hasHeading&&result.hasInstructions&&!result.hasBetaBanner&&result.consentPreserved&&result.newBrand;
console.log('PRODUCTION_PR48_VERIFICATION '+JSON.stringify({...result,passed}));
if(!passed)process.exitCode=1;
