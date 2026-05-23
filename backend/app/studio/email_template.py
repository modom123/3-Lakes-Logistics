"""Email-safe HTML template built from 3 Lakes brand materials.

Uses inline CSS only (email-safe). Matches brand palette from the official
design materials: #0B2545 hero, #061629 stat bar, #34D399 accent, #4FB3F2 blue.
"""
from __future__ import annotations

from .registry import BOOKING_URL, WEBSITE_URL, BRAND_STATS, CHANNEL_COPY, SIGNUP_URL


def build_html(state: str = "", lead_name: str = "there") -> str:
    copy = CHANNEL_COPY["email"]
    subject_state = f" in {state}" if state else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>3 Lakes Logistics</title>
</head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" role="presentation"
       style="background:#f0f4f8;padding:24px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" role="presentation"
       style="max-width:600px;width:100%;">

  <!-- Header -->
  <tr>
    <td style="background:#0B2545;padding:20px 32px;border-radius:8px 8px 0 0;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
        <tr>
          <td>
            <span style="display:inline-block;width:32px;height:32px;background:#4FB3F2;
                         border-radius:6px;text-align:center;line-height:32px;
                         font-weight:700;color:#0B2545;font-size:14px;">3L</span>
            <span style="color:#F5F8FB;font-size:15px;font-weight:600;
                         vertical-align:middle;margin-left:10px;">3 Lakes Logistics</span>
          </td>
          <td align="right">
            <span style="color:#34D399;font-size:11px;letter-spacing:0.12em;
                         text-transform:uppercase;">Founders · Live</span>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Hero -->
  <tr>
    <td style="background:#0B2545;padding:40px 32px 32px;">
      <p style="margin:0 0 6px;color:#34D399;font-size:11px;
                letter-spacing:0.18em;text-transform:uppercase;">
        Open loads{subject_state}
      </p>
      <h1 style="margin:0 0 16px;color:#F5F8FB;font-size:40px;
                 font-weight:700;line-height:1.05;letter-spacing:-0.02em;">
        {copy["hero"]}
      </h1>
      <p style="margin:0;color:rgba(245,248,251,0.75);font-size:16px;line-height:1.6;">
        {copy["subhead"]}
      </p>
    </td>
  </tr>

  <!-- Stats bar -->
  <tr>
    <td style="background:#061629;padding:28px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
        <tr>
          <td width="33%" style="text-align:center;padding:0 8px;">
            <div style="color:#4FB3F2;font-size:32px;font-weight:700;
                        letter-spacing:-0.03em;">{copy["stat_1_label"]}</div>
            <div style="color:rgba(245,248,251,0.6);font-size:12px;
                        margin-top:4px;">{copy["stat_1_desc"]}</div>
          </td>
          <td width="33%" style="text-align:center;padding:0 8px;
                                  border-left:1px solid rgba(245,248,251,0.1);
                                  border-right:1px solid rgba(245,248,251,0.1);">
            <div style="color:#34D399;font-size:32px;font-weight:700;
                        letter-spacing:-0.03em;">{copy["stat_2_label"]}</div>
            <div style="color:rgba(245,248,251,0.6);font-size:12px;
                        margin-top:4px;">{copy["stat_2_desc"]}</div>
          </td>
          <td width="33%" style="text-align:center;padding:0 8px;">
            <div style="color:#F5F8FB;font-size:32px;font-weight:700;
                        letter-spacing:-0.03em;">{copy["stat_3_label"]}</div>
            <div style="color:rgba(245,248,251,0.6);font-size:12px;
                        margin-top:4px;">{copy["stat_3_desc"]}</div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Body copy -->
  <tr>
    <td style="background:#0f1e33;padding:32px;
               border-bottom:1px solid rgba(245,248,251,0.08);">
      <p style="margin:0;color:rgba(245,248,251,0.8);font-size:15px;line-height:1.7;">
        Hi {lead_name},
      </p>
      <p style="margin:16px 0 0;color:rgba(245,248,251,0.8);font-size:15px;line-height:1.7;">
        {copy["body"].replace(chr(10), "<br><br>")}
      </p>
    </td>
  </tr>

  <!-- CTA -->
  <tr>
    <td style="background:#0f1e33;padding:24px 32px 36px;text-align:center;">
      <a href="{BOOKING_URL}"
         style="display:inline-block;background:#4FB3F2;color:#0B2545;
                font-weight:700;font-size:15px;padding:14px 32px;
                border-radius:6px;text-decoration:none;letter-spacing:0.01em;">
        {copy["cta"]}
      </a>
      <p style="margin:16px 0 0;color:rgba(245,248,251,0.45);font-size:13px;">
        Or view the full platform overview:
        <a href="{WEBSITE_URL}/demo" style="color:#4FB3F2;text-decoration:none;">
          {WEBSITE_URL}/demo
        </a>
      </p>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="background:#061629;padding:20px 32px;border-radius:0 0 8px 8px;">
      <table width="100%" cellpadding="0" cellspacing="0" role="presentation">
        <tr>
          <td style="color:rgba(245,248,251,0.4);font-size:11px;line-height:1.6;">
            3 Lakes Logistics LLC · FMCSA Licensed · Bonded · Insured<br>
            <a href="{WEBSITE_URL}/unsubscribe"
               style="color:rgba(245,248,251,0.4);text-decoration:underline;">
              Unsubscribe
            </a>
            &nbsp;·&nbsp;
            <a href="{WEBSITE_URL}"
               style="color:rgba(245,248,251,0.4);text-decoration:underline;">
              {WEBSITE_URL}
            </a>
          </td>
          <td align="right">
            <span style="display:inline-block;width:28px;height:28px;background:#4FB3F2;
                         border-radius:5px;text-align:center;line-height:28px;
                         font-weight:700;color:#0B2545;font-size:12px;">3L</span>
          </td>
        </tr>
      </table>
    </td>
  </tr>

</table>
</td></tr>
</table>
</body>
</html>"""
