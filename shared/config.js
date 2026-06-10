// 3 Lakes Logistics — Shared Configuration
// API_BASE is injected at build time by scripts/inject-config.js via API_BASE_URL env var.
// Driver auth uses per-user session tokens obtained at login — no static API token in client code.
(function(){
  var C = window.__3LL_CONFIG = window.__3LL_CONFIG || {};
  C.SUPABASE_URL = 'https://zngipootstubwvgdmckt.supabase.co';
  // Supabase anon key is intentionally public; all access is restricted by Row Level Security policies.
  C.SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpuZ2lwb290c3R1Ynd2Z2RtY2t0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMxMjk3ODUsImV4cCI6MjA4ODcwNTc4NX0.6MXR8q-CKVuiiJaJKuckxABAUQ-siuyP0-KoaLkt33g';
  C.API_BASE     = window.__3LL_API_BASE  || 'https://three-lakes-logistics-api.onrender.com';
  C.SENTRY_DSN   = window.__3LL_SENTRY_DSN || '';
  try { localStorage.removeItem('3LL_API_BASE'); localStorage.removeItem('3LL_API_TOKEN'); } catch(e){}
  window.__3LL_API_BASE = C.API_BASE;
})();

