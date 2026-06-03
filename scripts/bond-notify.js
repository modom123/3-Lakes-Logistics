/**
 * Bond Notification — Email report to Mark, Cece, and owner after Bond runs
 *
 * Sends via Hostinger SMTP (smtp.hostinger.com:465) from info@3lakeslogistics.com
 *
 * Set before running Bond:
 *   $env:BOND_EMAIL_PASS = "your_info@3lakeslogistics.com_password"
 *
 * Or Bond will prompt for it once and remember for the session.
 */

const { execSync, spawnSync } = require('child_process');
const path    = require('path');
const https   = require('https');

function hasMod(m) { try { require.resolve(m); return true; } catch { return false; } }
if (!hasMod('nodemailer')) {
  console.log('  [notify] Installing nodemailer...');
  execSync('npm install nodemailer --no-save', { cwd: path.join(__dirname, '..'), stdio: 'pipe' });
}

const nodemailer = require('nodemailer');
const readline   = require('readline');

const SMTP_HOST = 'smtp.hostinger.com';
const SMTP_PORT = 465;
const FROM_ADDR = 'info@3lakeslogistics.com';

// Recipients: Mark Odom office, Cece (CC office), owner
const TO = [
  'mark@3lakeslogistics.com',
  'cece@3lakeslogistics.com',
  'nwtcinvestment@gmail.com',
];

function promptPass() {
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question('\n[Bond] Email password for info@3lakeslogistics.com: ', ans => {
      rl.close();
      resolve(ans.trim());
    });
  });
}

/**
 * sendBondReport(steps)
 *
 * steps: array of { name, status ('ok'|'fail'|'skip'), detail }
 */
async function sendBondReport(steps) {
  const pass = process.env.BOND_EMAIL_PASS || await promptPass();
  if (!pass) {
    console.log('  [notify] No email password — skipping report email.');
    return;
  }

  const now   = new Date().toLocaleString('en-US', { timeZone: 'America/Detroit', dateStyle: 'full', timeStyle: 'short' });
  const allOk = steps.every(s => s.status !== 'fail');

  const statusIcon  = s => s.status === 'ok' ? '✅' : s.status === 'fail' ? '❌' : '⏭️';
  const statusColor = s => s.status === 'ok' ? '#16a34a' : s.status === 'fail' ? '#dc2626' : '#6b7280';

  const rows = steps.map(s => `
    <tr>
      <td style="padding:10px 14px;border-bottom:1px solid #1e3a5f;font-size:15px;">${statusIcon(s)}</td>
      <td style="padding:10px 14px;border-bottom:1px solid #1e3a5f;color:#e2e8f0;font-size:15px;">${s.name}</td>
      <td style="padding:10px 14px;border-bottom:1px solid #1e3a5f;color:${statusColor(s)};font-size:13px;">${s.detail || (s.status === 'ok' ? 'Completed' : s.status === 'fail' ? 'Failed' : 'Skipped')}</td>
    </tr>`).join('');

  const html = `<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0a0f1e;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0f1e;padding:32px 0;">
    <tr><td align="center">
      <table width="620" cellpadding="0" cellspacing="0" style="background:#0d1b36;border-radius:12px;overflow:hidden;border:1px solid #1e3a5f;">

        <!-- Header -->
        <tr><td style="background:linear-gradient(135deg,#1a3a6b,#0d2347);padding:28px 32px;">
          <div style="font-size:13px;color:#64b5f6;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;">3 Lakes Logistics — Automated Agent</div>
          <div style="font-size:26px;font-weight:700;color:#ffffff;">Bond Deployment Report</div>
          <div style="font-size:13px;color:#90caf9;margin-top:6px;">${now} · Eastern Time</div>
        </td></tr>

        <!-- Status Banner -->
        <tr><td style="background:${allOk ? '#14532d' : '#7f1d1d'};padding:14px 32px;text-align:center;">
          <span style="font-size:16px;font-weight:600;color:#fff;">${allOk ? '✅ All steps completed successfully' : '⚠️ Some steps need attention'}</span>
        </td></tr>

        <!-- Steps Table -->
        <tr><td style="padding:24px 32px 8px;">
          <div style="font-size:12px;color:#64b5f6;letter-spacing:1px;text-transform:uppercase;margin-bottom:12px;">Step-by-Step Results</div>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-radius:8px;overflow:hidden;border:1px solid #1e3a5f;">
            <tr style="background:#112244;">
              <th style="padding:10px 14px;text-align:left;font-size:11px;color:#64b5f6;letter-spacing:1px;text-transform:uppercase;width:40px;"></th>
              <th style="padding:10px 14px;text-align:left;font-size:11px;color:#64b5f6;letter-spacing:1px;text-transform:uppercase;">Step</th>
              <th style="padding:10px 14px;text-align:left;font-size:11px;color:#64b5f6;letter-spacing:1px;text-transform:uppercase;">Result</th>
            </tr>
            ${rows}
          </table>
        </td></tr>

        <!-- Next Steps -->
        <tr><td style="padding:20px 32px 8px;">
          <div style="font-size:12px;color:#64b5f6;letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;">Remaining Actions</div>
          <ul style="color:#94a3b8;font-size:14px;line-height:1.8;margin:0;padding-left:20px;">
            <li>Create Google Play service account → run <code style="color:#60a5fa;">node scripts\\encode-play-key.js</code></li>
            <li>Create app listings in Play Console (Truck Driver + Light Fleet)</li>
            <li>Upload signed AABs to internal track after builds complete</li>
            <li>Complete store listing, content rating, and data safety form</li>
          </ul>
        </td></tr>

        <!-- Monitor Link -->
        <tr><td style="padding:20px 32px 28px;">
          <a href="https://github.com/modom123/3-lakes-logistics/actions"
             style="display:inline-block;background:#1a56db;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-size:14px;font-weight:600;">
            Monitor GitHub Actions →
          </a>
        </td></tr>

        <!-- Footer -->
        <tr><td style="background:#0a0f1e;padding:16px 32px;border-top:1px solid #1e3a5f;">
          <div style="font-size:12px;color:#475569;">This is an automated report from Bond, the 3 Lakes Logistics deployment agent.</div>
        </td></tr>

      </table>
    </td></tr>
  </table>
</body>
</html>`;

  const text = `Bond Deployment Report — ${now}\n\n` +
    steps.map(s => `${statusIcon(s)} ${s.name}: ${s.detail || s.status}`).join('\n') +
    `\n\nMonitor: https://github.com/modom123/3-lakes-logistics/actions`;

  const transporter = nodemailer.createTransport({
    host: SMTP_HOST,
    port: SMTP_PORT,
    secure: true,
    auth: { user: FROM_ADDR, pass },
  });

  try {
    await transporter.verify();
    await transporter.sendMail({
      from:    `"Bond — 3 Lakes Logistics" <${FROM_ADDR}>`,
      to:      TO.join(', '),
      subject: `Bond Report — ${allOk ? 'All Steps Complete' : 'Action Required'} — ${new Date().toLocaleDateString('en-US')}`,
      html,
      text,
    });
    console.log(`\n  [notify] ✅ Report emailed to: ${TO.join(', ')}`);
  } catch (err) {
    console.log(`\n  [notify] ⚠️  Email failed (${err.message}) — report printed above in terminal only.`);
  }
}

module.exports = { sendBondReport };
