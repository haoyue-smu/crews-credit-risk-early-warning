# Sample inputs

`dummy_financials.xml` is a fictional company ("Acme Manufacturing Corp") with one year of
income statement, balance sheet and cash flow figures. Upload it on the Case Entry page to
run the Financial Ingestion (FIS) stage without any real filing.

## Using real public filings

FIS also accepts PDF, XML and XBRL filings. Download them yourself from the official
public sources; none are bundled in this repo:

- **US-listed companies:** annual reports (Form 10-K) from SEC EDGAR,
  <https://www.sec.gov/edgar/search/>
- **SGX-listed companies:** annual reports from SGX company announcements,
  <https://www.sgx.com/securities/company-announcements>, or the company's investor
  relations page
- **Other markets:** the company's investor relations page, or the exchange's filing portal

Uploaded files are saved under `data/uploads/`, which is git-ignored.
