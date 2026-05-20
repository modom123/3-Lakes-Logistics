// 3 Lakes Logistics — Shared Configuration
// API_BASE and API_TOKEN are injected at build time by scripts/inject-config.js
// using Vercel env vars: API_BASE_URL and API_BEARER_TOKEN
(function(){
  var C = window.__3LL_CONFIG = window.__3LL_CONFIG || {};
  C.SUPABASE_URL  = 'https://zngipootstubwvgdmckt.supabase.co';
  C.SUPABASE_KEY  = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpuZ2lwb290c3R1Ynd2Z2RtY2t0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMxMjk3ODUsImV4cCI6MjA4ODcwNTc4NX0.6MXR8q-CKVuiiJaJKuckxABAUQ-siuyP0-KoaLkt33g';
  C.API_BASE      = window.__3LL_API_BASE || 'https://three-lakes-logistics-api.onrender.com';
  C.API_TOKEN     = window.__3LL_API_TOKEN || 'taiOFL40cCr5V0pH89hUks8jXVPlOkm2WxKvd3f6BoE';
  // Clear any stale cached values from localStorage
  try { localStorage.removeItem('3LL_API_BASE'); localStorage.removeItem('3LL_API_TOKEN'); } catch(e){}
  window.__3LL_API_BASE  = C.API_BASE;
  window.__3LL_API_TOKEN = C.API_TOKEN;
})();

