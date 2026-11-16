# GST FINDER

A Streamlit educational GST search and calculation app for India.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Keep `app.py`, `requirements.txt`, and `gst_master_database.csv` together.

## Features
- First screen offers Sign In, Register, and Continue as Guest.
- Passwords are stored as PBKDF2-HMAC-SHA256 hashes with random salts.
- Guest history is not persisted. Registered users can view and delete their own history.
- Product name / optional HSN search with a matching dropdown showing product name and HSN; selecting a result reveals the associated HSN and record.
- No product category or manufacturer filter.
- GST calculator, indicative taxable-value helper, bill preview and TXT/PDF/DOCX downloads.
- Master CSV download from INFO.

## Source data and legal limitations
The master CSV was generated from the supplied consolidated research file's CBIC goods-rate table. That source explicitly labels the schedule 01-04-2023. Accordingly, rows are labelled historical and must not be treated as current verified GST rates. Search aliases for everyday terms (including shampoo and toothpaste) are lookup aids only, not independent legal classification decisions. Exact HSN and rate depend on product facts, tariff notes and subsequent notifications. Unavailable rates remain blank rather than fabricated.

The app is not an official government platform or substitute for professional advice. Before production use, review security, deployment persistence, DPDP compliance, current official notifications and all product classifications. Streamlit Community Cloud local SQLite storage is not a durable production database.
