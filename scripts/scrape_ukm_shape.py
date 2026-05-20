# Crawl UKMShape International Student Guides and Ingest to RAG
#
# Usage:
#   python scripts/scrape_ukm_shape.py

import sys
import urllib3
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Relevant public pages for UKM international students on UKMShape website
SHAPE_URLS = [
    {
        "category": "Visa & Student Pass Guide",
        "url": "https://www.ukm.my/ukmshape/visa-and-student-pass/",
        "key_points": [
            "VAL (Visa Approval Letter) requirements.",
            "Single Entry Visa (SEV) requirements before entering Malaysia.",
            "Student Pass endorsement steps upon arrival.",
            "Dependent Pass regulations for student families.",
            "Renewal applications: must be submitted at least 3 months (90 days) before expiry."
        ]
    },
    {
        "category": "Medical Check-Up Guide",
        "url": "https://www.ukm.my/ukmshape/medical-check-up/",
        "key_points": [
            "Mandatory medical screening within 7 days of arrival in Malaysia.",
            "Must be done at EMGS panel clinics or UKM Health Centre (Pusat Kesihatan UKM).",
            "Required documents: Passport, Medical Examination Form, and Letter of Offer.",
            "Failure to pass the medical checkup may lead to student visa cancellation."
        ]
    },
    {
        "category": "Student Accommodation",
        "url": "https://www.ukm.my/ukmshape/student-housing/",
        "key_points": [
            "On-campus residential colleges (Kolej Kediaman) details.",
            "Off-campus private rental options around Bangi, Kajang, and Semenyih.",
            "Booking procedures, fees, and rules for international students."
        ]
    },
    {
        "category": "Academic Calendar",
        "url": "https://www.ukm.my/ukmshape/academic-calendar/",
        "key_points": [
            "Semester structures for undergraduate and postgraduate studies.",
            "Important periods: Course registration, lecture weeks, mid-semester breaks, and exam weeks."
        ]
    }
]


def clean_web_text(soup):
    """Extract clean, printable text from BeautifulSoup object."""
    # Decompose script and style tags
    for element in soup(["script", "style", "nav", "footer", "header", "aside"]):
        element.decompose()
    
    # Try to find main content areas
    main_content = soup.find('main') or soup.find(id='content') or soup.find(class_='content') or soup.body
    if not main_content:
        return ""
        
    text = main_content.get_text(separator='\n')
    
    # Clean up empty lines and long white-spaces
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    cleaned_lines = []
    for line in lines:
        if len(line) > 5 and not line.startswith("http"):
            cleaned_lines.append(line)
            
    return "\n".join(cleaned_lines)


def crawl_shape_page(item):
    """Crawl a UKMShape page safely."""
    url = item["url"]
    cat = item["category"]
    print(f"[*] Crawling UKMShape page: {cat} ({url}) ...")
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    
    scraped_data = {
        "status": "Failed",
        "title": "N/A",
        "content": ""
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15, verify=False)
        if response.status_code == 200:
            scraped_data["status"] = "Success"
            soup = BeautifulSoup(response.text, "html.parser")
            
            title_tag = soup.find("title")
            scraped_data["title"] = title_tag.get_text().strip() if title_tag else cat
            
            clean_text = clean_web_text(soup)
            scraped_data["content"] = clean_text[:6000] # Limit content size to avoid oversized database chunks
            print(f"    [+] Successfully crawled {len(clean_text)} characters.")
        else:
            scraped_data["status"] = f"HTTP {response.status_code}"
            print(f"    [!] Received HTTP {response.status_code} for {url}")
            
    except Exception as e:
        scraped_data["status"] = f"Error: {str(e)}"
        print(f"    [!] Error crawling {url}: {e}")
        
    return scraped_data


def save_guide_file(all_results):
    """Save the crawled results into a RAG text file."""
    output_dir = PROJECT_ROOT / "data" / "ukm_ftsm"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "ukm_shape_admission_visa_guide.txt"
    
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("UKMShape International Student Guide (Visa, Housing, Medical & Calendar)\n")
        f.write("Source: UKMShape Official Website (Crawled Automatically)\n")
        f.write(f"Crawled at: {datetime.now().isoformat()}\n")
        f.write("Language: English (UKM Official International Page)\n")
        f.write("=" * 80 + "\n\n")
        
        for idx, item in enumerate(SHAPE_URLS, 1):
            res = all_results[item["url"]]
            
            f.write(f"[Topic {idx}] {item['category']}\n")
            f.write(f"Source URL: {item['url']}\n")
            f.write(f"Crawled Status: {res['status']}\n")
            f.write(f"Page Title: {res['title']}\n")
            
            f.write("\n--- Critical Reference Points ---\n")
            for kp in item["key_points"]:
                f.write(f"- {kp}\n")
                
            f.write("\n--- Crawled Website Details ---\n")
            if res["content"]:
                f.write(res["content"])
            else:
                f.write("Could not retrieve text content directly. Please refer to the Source URL.")
                
            f.write("\n\n" + "=" * 80 + "\n\n")
            
    print(f"\n[+] UKMShape admission & visa guide saved to: {out_file}")
    return out_file


def retrain_chroma():
    """Trigger the RAG ingestion to train the new dataset."""
    print("\n" + "=" * 60)
    print("Retraining RAG Vector Database (ChromaDB)...")
    print("=" * 60)
    try:
        from rag.vector_store import VectorStoreService
        vs = VectorStoreService()
        vs.load_document()
        print("\n[+] Success! ChromaDB database has been retrained with UKMShape international guides.")
    except Exception as e:
        print(f"\n[!] Error during Chroma DB retraining: {e}", file=sys.stderr)


def main():
    print("=" * 70)
    print("UKMShape International Student Portal Crawler")
    print("=" * 70)
    
    results = {}
    for item in SHAPE_URLS:
        results[item["url"]] = crawl_shape_page(item)
        print("-" * 50)
        
    save_guide_file(results)
    retrain_chroma()
    
    print("\n" + "=" * 70)
    print("ALL DONE! The UKMShape international student guides are fully integrated.")
    print("=" * 70)


if __name__ == "__main__":
    main()
