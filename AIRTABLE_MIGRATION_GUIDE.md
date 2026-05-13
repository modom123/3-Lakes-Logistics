# Airtable → Supabase Lead Migration Guide

This guide shows how to migrate your 129 leads from Airtable into the Ops Suite and Supabase.

## Quick Start

### 1. Get Your Airtable Credentials

Visit your Airtable workspace:

1. **API Key:**
   - Go to https://airtable.com/account/api
   - Create or copy an existing API token
   - Copy the token value

2. **Base ID:**
   - Open your leads base
   - Click the "?ⓘ" icon (top right)
   - Copy the Base ID (looks like: `appXXXXXXXXXXXXXX`)

3. **Table Name:**
   - Note the name of your leads table (usually "Leads" or "table 1")

### 2. Configure .env File

Create `.env` in the project root with:

```bash
# Airtable
AIRTABLE_API_KEY=your_api_token_here
AIRTABLE_BASE_ID=appXXXXXXXXXXXXXX

# Supabase (already configured)
SUPABASE_URL=https://zngipootstubwvgdmckt.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_key_here
```

### 3. Run Migration

Choose one of these methods:

#### Option A: Python Script (Recommended)

```bash
# Install dependencies
pip install supabase

# Run migration from project root
python migrate_airtable_to_supabase.py
```

The script will:
- ✅ Validate credentials
- ✅ Test Airtable connection
- ✅ Fetch all records
- ✅ Transform into lead format
- ✅ Insert into Supabase
- ✅ Show success summary

#### Option B: API Endpoint

If your backend is running:

```bash
# Start backend
cd backend
uvicorn app.main:app --reload --port 8080

# In another terminal, trigger migration
curl -X POST http://localhost:8080/api/migrate/airtable-leads \
  -H "Authorization: Bearer your_api_token"
```

#### Option C: Ops Suite UI (Coming Soon)

Once deployed, you'll see a "Migrate Leads" button in the Ops Suite.

## Field Mapping

Your Airtable fields map to Supabase like this:

| Airtable Field | Supabase Field | Notes |
|---|---|---|
| Company Name | prospect_name | Required |
| Phone | phone_number | Required |
| Location | (in notes) | Optional |
| Truck Type | (in notes) | Optional |
| Website | (in notes) | Optional |
| Rating | (in notes) | Optional |

Extra fields are preserved in the `notes` field.

## Verify Migration

### In Supabase

1. Go to https://app.supabase.com
2. Select your project
3. Click "SQL Editor"
4. Run:
   ```sql
   SELECT COUNT(*) as total_leads FROM leads WHERE source = 'airtable_migration';
   ```

### In Ops Suite

1. Open `index.html` in browser
2. Go to **Leads** page
3. Filter by Source = "airtable_migration"
4. You should see all 129 leads

## Troubleshooting

### Error: "Invalid Airtable API key"
- Check that your token is copied correctly
- Tokens expire after 20 years; if very old, create a new one
- Make sure `.env` is in the project root

### Error: "Airtable base or table not found"
- Verify Base ID is correct (copy from https://airtable.com/api)
- Check that the table name matches exactly (case-sensitive)
- Confirm you have permission to access the base

### Error: "Could not connect to Supabase"
- Verify `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are correct
- Check your Supabase project settings
- Ensure your IP isn't blocked by firewall

### No records found
- Verify your Airtable table isn't empty
- Check table permissions
- Try fetching manually:
  ```bash
  curl -H "Authorization: Bearer YOUR_TOKEN" \
    https://api.airtable.com/v0/YOUR_BASE/table%201
  ```

## After Migration

Once leads are in Supabase:

1. ✅ **Vance can start calling** - Prospecting agent sees all 129 leads
2. ✅ **Dashboard updated** - Ops Suite shows lead metrics
3. ✅ **Follow-ups active** - Interested prospects get demo email + SMS
4. ✅ **Conversion tracked** - See which leads book demos

## Next Steps

- [ ] Run migration script
- [ ] Verify count in Supabase (should be 129)
- [ ] Check Ops Suite for leads
- [ ] Start first Vance call
- [ ] Monitor conversion metrics

## Support

If you hit issues:

1. Check `.env` exists and has correct format
2. Run `python migrate_airtable_to_supabase.py` with verbose output
3. Check Airtable API limits (generous, but exists)
4. Verify Supabase quotas haven't been exceeded

## FAQ

**Q: Will this duplicate leads if I run it twice?**
A: Yes. Each run inserts fresh records. Run once, or add deduplication logic if needed.

**Q: Can I update fields after migration?**
A: Yes. Edit leads in Supabase or Ops Suite. Changes are live.

**Q: Does this delete anything in Airtable?**
A: No. Migration is read-only from Airtable. Your original data is safe.

**Q: How long does 129 leads take?**
A: < 2 minutes for the full migration.

---

Ready? Start with **Option A: Python Script** above.
