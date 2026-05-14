// 3 Lakes Logistics — Shared Configuration
// Edit this one file to update credentials/URLs across all 4 parts
(function(){
  var C = window.__3LL_CONFIG = window.__3LL_CONFIG || {};
  C.SUPABASE_URL  = 'https://zngipootstubwvgdmckt.supabase.co';
  C.SUPABASE_KEY  = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpuZ2lwb290c3R1Ynd2Z2RtY2t0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMxMjk3ODUsImV4cCI6MjA4ODcwNTc4NX0.6MXR8q-CKVuiiJaJKuckxABAUQ-siuyP0-KoaLkt33g';
  C.API_BASE      = window.__3LL_API_BASE || localStorage.getItem('3LL_API_BASE') || 'http://localhost:8080';
  C.API_TOKEN     = window.__3LL_API_TOKEN || localStorage.getItem('3LL_API_TOKEN') || 'change-me-in-prod';
  // Expose globals for backwards compat
  window.__3LL_API_BASE  = C.API_BASE;
  window.__3LL_API_TOKEN = C.API_TOKEN;
})();
