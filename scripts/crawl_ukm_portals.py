# Crawl UKM Student Portals and Ingest to RAG
#
# Usage:
#   python scripts/crawl_ukm_portals.py

import asyncio
import os
import sys
import urllib3
from pathlib import Path
from datetime import datetime

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Define the portals with metadata, instructions, and user tips
PORTALS = [
    {
        "id": "smp",
        "name": "教务系统 SMP (Academic System)",
        "url": "https://smplucee.ukm.my",
        "desc": "学校学生主页。主要用于每学期开始时的选课（Course Registration）以及期末查询成绩（Check Results/Exam Grades）。",
        "tips": [
            "每学期选课阶段服务器可能会比较拥堵，建议提前登录守候。",
            "期末查成绩需要先在SPPP（教评系统）中完成对老师的评价，否则无法在SMP中看到成绩。",
            "选课时注意检查先修课程（Prerequisites）要求是否已满足。"
        ]
    },
    {
        "id": "ekewangan",
        "name": "财务系统 EKEWANGAN (Financial System)",
        "url": "https://ekewangan.ukm.my/",
        "desc": "用于查询学生账单、缴纳学费及其他学杂费。",
        "tips": [
            "交学费时，推荐使用能够直接兑换马币（MYR）的银行卡/信用卡付款，这样相比于通过美元（USD）结算会更便宜，能省下一笔汇率差价。",
            "交费完成后，务必下载并妥善保存好 PDF 格式的官方付款收据（Receipt），因为后续签证续签或注册时可能需要上传此凭证作为缴费证明。"
        ]
    },
    {
        "id": "folio",
        "name": "上课系统 FOLIO (Learning Management System)",
        "url": "https://ukmfolio.ukm.my/",
        "desc": "UKM 的官方在线学习管理系统。老师会在此系统发布课件资料（Courseware）、课程大纲、作业提交通知、小测验以及期末在线考试等。",
        "tips": [
            "部分课程的老师可能会选用 Microsoft Teams 或者 Google Classroom 进行授课或通知，开学第一堂课务必向老师确认使用的授课平台。",
            "建议每周定期登录 FOLIO 检查是否有新作业或课程通知，避免遗漏重要截止日期（Deadlines）。"
        ]
    },
    {
        "id": "library",
        "name": "图书馆系统 (PTSL Library System)",
        "url": "https://eresourcesptsl.ukm.remotexs.co/user/login?destination=database",
        "desc": "UKM 图书馆电子资源系统，提供海量学术论文、电子书、数据库（如 IEEE, ScienceDirect）的检索与下载服务。",
        "tips": [
            "请使用你的 UKM 学生账号（学号）和密码进行登录。",
            "在校外或宿舍使用时必须通过此 remotexs 代理网址登录，才能免费下载学校购买的付费数据库资源。"
        ]
    },
    {
        "id": "sppp",
        "name": "教评系统 SPPP (Course Evaluation System)",
        "url": "https://appsmu.ukm.my/sppp/",
        "desc": "每学期末学生对任课教师和课程教学质量进行在线评估的系统。",
        "tips": [
            "【至关重要】在每学期期末考试前后，学校会开放 SPPP 系统。你必须在截止日期前，对当前学期的所有课程和老师完成教学评价（Evaluation）。",
            "如果未在截止日期前完成评价，系统会锁定你的成绩，导致你无法在教务系统（SMP）中查询期末考试成绩，甚至可能影响下学期选课。"
        ]
    },
    {
        "id": "ukmcard",
        "name": "学生卡系统 UKMCARD",
        "url": "https://appsmu.ukm.my/ukmcard/",
        "desc": "用于查询、申请学生卡以及检查学生卡的制作和可领取状态。",
        "tips": [
            "新生入学完成线上和线下注册后，可以在该系统查询自己学生卡的制作进度。",
            "显示为‘可领取（Ready for collection）’状态后，方可前往指定地点（通常是 Pusanika 4楼或学院行政办公室）领取实体学生卡。"
        ]
    },
    {
        "id": "email",
        "name": "学生邮箱系统 SISWAMAIL / SPEEP",
        "url": "http://appsmu.ukm.my/speep/index.php",
        "desc": "学生专属电子邮箱（后缀通常为 @siswa.ukm.edu.my）的注册和激活入口。",
        "tips": [
            "新生在完成注册后，需要登录此 speep 网址进行学生邮箱的初始开通与密码设置。初始密码通常为你的护照号码（Passport Number）。",
            "邮箱成功开通后，日常登录可以直接使用 Gmail 登录入口（http://mail.google.com/a/siswa.ukm.edu.my）登录，收发学校官方通知和课程邮件。"
        ]
    }
]


def crawl_portal(portal):
    """Crawl a single portal to fetch its public structure, titles, or forms safely."""
    url = portal["url"]
    name = portal["name"]
    print(f"[*] Crawling: {name} ({url}) ...")
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    
    crawled_info = {
        "status": "Unknown",
        "title": "N/A",
        "text": "N/A",
        "redirect_url": None
    }
    
    try:
        # Use a short timeout of 10s as some internal servers might be slow or offline
        response = requests.get(url, headers=headers, timeout=10, verify=False, allow_redirects=True)
        crawled_info["status"] = f"HTTP {response.status_code}"
        
        # Capture final URL after redirects
        if response.history:
            crawled_info["redirect_url"] = response.url
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get page title
        title_tag = soup.find('title')
        if title_tag:
            crawled_info["title"] = title_tag.get_text().strip()
        else:
            crawled_info["title"] = "No Title Found"
            
        # Extract main text content from landing page (like login prompt details)
        # Avoid heavy HTML templates
        for s in soup(["script", "style"]):
            s.decompose()
            
        text_content = soup.get_text(separator=' ')
        # Clean whitespaces
        words = [w.strip() for w in text_content.split() if w.strip()]
        cleaned_text = " ".join(words[:150]) # Get first 150 words
        crawled_info["text"] = cleaned_text if cleaned_text else "No text content found."
        
    except requests.exceptions.Timeout:
        crawled_info["status"] = "Timeout (Server took too long to respond)"
        print(f"    [!] Timeout while connecting to {url}")
    except Exception as e:
        crawled_info["status"] = f"Error: {str(e)}"
        print(f"    [!] Connection error for {url}: {e}")
        
    return crawled_info


def save_knowledge_file(crawled_results):
    """Save the crawled portal results and guides to RAG data directory."""
    output_dir = PROJECT_ROOT / "data" / "ukm_ftsm"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / "ukm_core_portals_guide.txt"
    
    with open(out_file, "w", encoding="utf-8") as f:
        f.write("UKM Essential Student Systems and Portals Guide\n")
        f.write("Source: Student community contribution & real-time automated portal crawling\n")
        f.write(f"Generated at: {datetime.now().isoformat()}\n")
        f.write("Language: Bilingual (Chinese & English)\n")
        f.write("=" * 80 + "\n\n")
        
        for i, portal in enumerate(PORTALS, 1):
            crawl_res = crawled_results[portal["id"]]
            
            f.write(f"[System Portal {i}] {portal['name']}\n")
            f.write(f"ID: {portal['id']}\n")
            f.write(f"Official URL: {portal['url']}\n")
            
            if crawl_res.get("redirect_url"):
                f.write(f"Redirected Login URL: {crawl_res['redirect_url']}\n")
                
            f.write(f"Public Portal Status: {crawl_res['status']}\n")
            f.write(f"Public Page Title: {crawl_res['title']}\n")
            f.write(f"System Purpose: {portal['desc']}\n")
            
            f.write("\n--- User Tips & Practical Guidance / 学生使用建议与省钱避坑指南 ---\n")
            for tip in portal["tips"]:
                f.write(f"- {tip}\n")
                
            f.write("\n--- Public Page Crawled Snippet / 公开网页抓取片段 ---\n")
            f.write(f"{crawl_res['text']}\n")
            f.write("\n" + "=" * 80 + "\n\n")
            
    print(f"\n[+] Knowledge base guide file successfully written to: {out_file}")
    return out_file


def retrain_chroma():
    """Retrain Chroma vector store to ingest the newly crawled portal guide."""
    print("\n" + "=" * 60)
    print("Retraining RAG Vector Database (ChromaDB) with new guides...")
    print("=" * 60)
    try:
        from rag.vector_store import VectorStoreService
        vs = VectorStoreService()
        # Ingest the documents (detects new files and re-indexes them)
        vs.load_document()
        print("\n[+] Success! ChromaDB database has been retrained with the new UKM portal guides.")
    except Exception as e:
        print(f"\n[!] Error during Chroma DB retraining: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()


def main():
    print("=" * 70)
    print("UKM Core Student Portals Crawler & RAG Integrator")
    print("=" * 70)
    
    results = {}
    for portal in PORTALS:
        res = crawl_portal(portal)
        results[portal["id"]] = res
        print(f"    [Result] Title: '{res['title']}', Status: {res['status']}")
        print("-" * 50)
        
    # Write the compiled guide to data path
    save_knowledge_file(results)
    
    # Trigger RAG database rebuild / reload
    retrain_chroma()
    
    print("\n" + "=" * 70)
    print("ALL DONE! The UKM core student systems guide is fully integrated.")
    print("=" * 70)


if __name__ == "__main__":
    main()
