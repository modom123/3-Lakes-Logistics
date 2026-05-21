"""Brand asset registry — copy, stats, and asset catalog extracted from marketing materials.

Agents import CHANNEL_COPY to write on-brand outreach. All stats sourced
from the official 3 Lakes marketing materials (brochure, sales deck, flyers).
"""
from __future__ import annotations

# ── Key stats (sourced from brand materials) ──────────────────────────────────

BRAND_STATS = {
    "flat_fee":              "$300/mo",
    "rpm_above_market":      "+22¢",
    "monthly_recovery":      "+$400",
    "automation_count":      "155+",
    "compliance":            "100%",
    "dispatcher_cut_saved":  "30%+",
    "paperwork_saved":       "14 hrs/wk",
    "monthly_leak":          "$1,200/mo",
    "founders_limit":        "1,000 trucks",
}

BRAND_TAGLINE   = "Automated American Trucking."
BRAND_VALUE_PROP = (
    "A flat-fee operating system for owner-operators — "
    "AI dispatch, paperless compliance, and revenue recovery on autopilot."
)
BRAND_HOOK      = "Your truck is leaking $1,200/mo."
BOOKING_URL     = "https://calendly.com/3lakes/commander-call"
WEBSITE_URL     = "https://3lakeslogistics.com"
SIGNUP_URL      = "https://3lakeslogistics.com/signup"

# ── Per-channel copy ──────────────────────────────────────────────────────────

CHANNEL_COPY: dict[str, dict[str, str]] = {
    "sms": {
        "new_lead":
            "Your truck loses $1,200/mo to dispatch fees. 3 Lakes fixes that — "
            "$300/mo flat, you keep 100% of earnings. Reply YES or book: {booking_url} "
            "Reply STOP to opt out.",
        "warm_lead":
            "3 Lakes Logistics: +22¢ RPM above market + $400/mo in recovered claims. "
            "$300/mo, no contracts. Interested? {booking_url} Reply STOP to opt out.",
        "re_engagement":
            "Still running with a 30%+ dispatch cut? 3 Lakes charges $300/mo flat. "
            "Keep everything else. {booking_url} Reply STOP to opt out.",
        "open_loads":
            "Open loads in {state} right now. 3 Lakes auto-dispatches to your app — "
            "$300/mo, keep 100%. {booking_url} Reply STOP to opt out.",
    },
    "email": {
        "subject_pitch":       "Your truck is leaking $1,200/mo — 3 Lakes Logistics",
        "subject_open_loads":  "Open loads in {state} — 3 Lakes Logistics",
        "subject_founders":    "Founders pricing closes at 1,000 trucks — 3 Lakes",
        "hero":                "Your truck is leaking $1,200/mo.",
        "subhead":             "AI dispatch. Paperless compliance. Revenue recovery. One flat fee.",
        "stat_1_label":        "+22¢",
        "stat_1_desc":         "above-market RPM, every load",
        "stat_2_label":        "+$400/mo",
        "stat_2_desc":         "in recovered detention + lumper claims",
        "stat_3_label":        "$300/mo",
        "stat_3_desc":         "flat rate — keep 100% of earnings",
        "body":
            "Most dispatchers take 30%+ off the top. Paperwork eats 14 hours a week. "
            "And the $400/mo in detention and lumper fees? Most carriers never even file them.\n\n"
            "3 Lakes Logistics is a flat-fee operating system: AI handles dispatch, "
            "compliance, paperwork, and revenue recovery — 155+ automations running 24/7.",
        "cta":                 "Book a 15-minute call →",
    },
    "voice": {
        "opener":
            "How long you been running your own authority?",
        "pain_hook":
            "Most carriers I talk to are losing about 30% to dispatch fees — "
            "before you even account for the paperwork time or the claims they never file.",
        "stat_pitch":
            "We charge $300 flat. You keep every dollar you earn. "
            "Our AI negotiates 22 cents above market on every load and files your detention automatically.",
        "cta":
            "Want me to get you 15 minutes with our Commander? Takes about 10 minutes to get you set up.",
        "objection_price":
            "That's less than a tank of diesel. And you're already paying 30% on every load — "
            "this replaces all of that.",
    },
    "social": {
        "open_loads":
            "Open loads. AI-negotiated rates. $300/mo flat. You keep 100%. "
            "155+ automations running while you drive. — 3 Lakes Logistics",
        "founder_program":
            "Your truck is leaking $1,200/mo. Dispatch fees. Missed claims. Paperwork hours. "
            "3 Lakes Logistics seals every leak for one flat fee. Founders: $300/mo for life.",
        "industry_tip":
            "Owner-operators leave $400/mo on the dock — unclaimed detention, TONU, and lumper fees. "
            "We file those automatically, every load.",
        "tiktok_hook":
            "Your truck loses $1,200 a month and you don't even see it happening.",
        "youtube_community":
            "Quick question for owner-operators — how much time do you spend on paperwork every week? "
            "Most carriers we talk to say 10-14 hours. We built a system that handles all of it. "
            "Curious what that looks like for your routes?",
    },
}

# ── Asset catalog ─────────────────────────────────────────────────────────────

ASSETS = [
    {
        "name":     "sales-deck",
        "title":    "3 Lakes Logistics Sales Deck",
        "type":     "presentation",
        "file":     "sales-deck.html",
        "description": "12-slide carrier briefing — full platform overview, pain points, pricing",
        "use_for":  ["sales_calls", "email_attachments", "follow_up"],
    },
    {
        "name":     "brochure",
        "title":    "Trifold Brochure",
        "type":     "brochure",
        "file":     "brochure.html",
        "description": "Print/digital trifold — problem/solution/pricing in 3 panels",
        "use_for":  ["email_follow_up", "print", "trade_shows"],
    },
    {
        "name":     "email-flyers",
        "title":    "Email Flyers",
        "type":     "flyer",
        "file":     "email-flyers.html",
        "description": "Founders urgency flyer + rate comparison flyer",
        "use_for":  ["email_campaigns", "social_posts"],
    },
    {
        "name":     "commercial-45s",
        "title":    "45s Commercial",
        "type":     "video_prototype",
        "file":     "commercial-45s.html",
        "description": "Full 45-second brand commercial with audio + animation",
        "use_for":  ["youtube_ads", "social_ads", "website"],
    },
    {
        "name":     "commercial-v2",
        "title":    "Commercial v2 (Custom Track)",
        "type":     "video_prototype",
        "file":     "commercial-v2.html",
        "description": "Alternative commercial with custom audio track",
        "use_for":  ["youtube_ads", "social_ads"],
    },
    {
        "name":     "youtube-ad-30s",
        "title":    "YouTube Pre-Roll Ad (30s)",
        "type":     "video_prototype",
        "file":     "youtube-ad-30s.html",
        "description": "30-second pre-roll optimised for YouTube skippable format",
        "use_for":  ["youtube_ads"],
    },
    {
        "name":     "brand-image",
        "title":    "Brand Image",
        "type":     "image",
        "file":     "brand-image.png",
        "description": "Primary brand visual — for social posts, TikTok, ads",
        "use_for":  ["social_posts", "tiktok", "ads", "email_header"],
    },
]
