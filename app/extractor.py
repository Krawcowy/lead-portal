import hashlib
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

KEYWORDS = [
    "syndyk", "licytacja", "sprzedaż", "sprzedaz",
    "upadłość", "upadlosc", "masa upadłości",
    "przetarg", "konkurs ofert", "cena wywoławcza", "wadium"
]

BAD_TITLES = [
    "home", "informacje", "komunikaty", "przetargi",
    "przetargi nierozstrzygnięte", "kontakt", "all",
    "new title", "zobacz listę", "lista aktualnych przetargów",
    "rodzaj przetargu", "nieruchomości", "ruchomości",
    "należności", "prawa", "inne"
]

def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()

def classify_asset_type(title, description):
    text = f"{title} {description}".lower()

    nieruchomosci = [
        "nieruchomość", "nieruchomosc", "lokal", "mieszkanie",
        "dom", "działka", "dzialka", "grunt", "budynek",
        "garaż", "garaz", "miejsce postojowe", "nieruchomości"
    ]

    ruchomosci = [
        "ruchomość", "ruchomosc", "ruchomości", "ruchomosci",
        "samochód", "samochod", "pojazd", "maszyna",
        "sprzęt", "sprzet", "wyposażenie", "wyposazenie",
        "piec", "meble", "komputer", "towar", "samochody"
    ]

    if any(word in text for word in nieruchomosci):
        return "nieruchomości"

    if any(word in text for word in ruchomosci):
        return "ruchomości"

    return "inne"

def classify_category(title, description):
    text = f"{title} {description}".lower()

    # --- NIERUCHOMOŚCI ---
    nieruchomosci = {
        "mieszkania": [
            "mieszkanie", "lokal mieszkalny",
            "spółdzielcze własnościowe", "spoldzielcze wlasnosciowe"
        ],
        "lokale użytkowe": [
            "lokal użytkowy", "lokal uzytkowy",
            "lokal usługowy", "lokal uslugowy",
            "biuro", "biurowy"
        ],
        "domy": [
            "dom", "budynek mieszkalny",
            "nieruchomość zabudowana", "nieruchomosc zabudowana"
        ],
        "działki / grunty": [
            "działka", "dzialka", "grunt", "grunty",
            "nieruchomość gruntowa", "nieruchomosc gruntowa"
        ],
        "garaże / miejsca postojowe": [
            "garaż", "garaz", "miejsce postojowe"
        ],
    }

    # --- RUCHOMOŚCI ---
    ruchomosci = {
        "samochody / pojazdy": [
            "samochód", "samochod", "pojazd",
            "auto", "ciągnik", "ciagnik",
            "naczepa", "przyczepa"
        ],
        "maszyny / sprzęt": [
            "maszyna", "maszyny",
            "sprzęt", "sprzet",
            "urządzenie", "urzadzenie",
            "linia produkcyjna", "piec"
        ],
        "wyposażenie / meble": [
            "wyposażenie", "wyposazenie",
            "meble", "biurka", "krzesła", "krzesla",
            "regały", "regaly"
        ],
        "towary / zapasy": [
            "towar", "towary",
            "zapasy", "magazyn",
            "materiały", "materialy"
        ],
    }

    # --- INNE ---
    inne = {
        "udziały / prawa": [
            "udział", "udzial", "udziały", "udzialy",
            "akcje", "wierzytelność", "wierzytelnosc",
            "prawa"
        ]
    }

    # 🔍 KOLEJNOŚĆ MA ZNACZENIE (najpierw dokładne)
    for group in [nieruchomosci, ruchomosci, inne]:
        for category, words in group.items():
            if any(word in text for word in words):
                return category

    return "inne"

def make_fake_url(source_url, title):
    slug = hashlib.md5(title.encode("utf-8")).hexdigest()[:12]
    return f"{source_url}#lead-{slug}"

def extract_price(text):
    patterns = [
        r"(?:cena wywoławcza|łączna cena wywoławcza|za cenę nie niższą niż|cena najmu|cena)\D{0,40}([0-9\s.,]+)\s*zł",
        r"([0-9\s.,]+)\s*zł"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            price = clean_text(match.group(1))
            return price + " zł"

    return None

def extract_deadline(text):
    patterns = [
        r"terminie do dnia\s+([0-9]{1,2}\s+\w+\s+[0-9]{4})",
        r"do dnia\s+([0-9]{1,2}\s+\w+\s+[0-9]{4})",
        r"do\s+([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_text(match.group(1))

    return None

def get_soup(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")

def build_lead(title, url, description):
    description = clean_text(description)

    asset_type = classify_asset_type(title, description)
    category = classify_category(title, description)

    return {
        "title": clean_text(title)[:300],
        "url": url,
        "description": description[:5000],
        "price": extract_price(description),
        "deadline": extract_deadline(description),
        "asset_type": asset_type,
        "category": category
    }

def extract_saltarski(source_url):
    leads = []
    seen = set()

    base_url = source_url.rstrip("/")

    page_urls = [base_url + "/"]

    for page_number in range(2, 11):
        page_urls.append(f"{base_url}/page/{page_number}/")

    for page_url in page_urls:
        try:
            soup = get_soup(page_url)
        except Exception as e:
            print(f"Nie udało się pobrać {page_url}: {e}")
            continue

        found_on_page = 0

        for a in soup.find_all("a", href=True):
            text = clean_text(a.get_text(" ", strip=True))
            href = urljoin(page_url, a["href"])

            if not text or len(text) < 40:
                continue

            lower = text.lower()

            if lower in BAD_TITLES:
                continue

            if "więcej" in lower and len(text) < 80:
                continue

            if not any(keyword in lower for keyword in KEYWORDS):
                continue

            parsed = urlparse(href)

            if "saltarski.com" not in parsed.netloc:
                continue

            if href in seen:
                continue

            seen.add(href)
            found_on_page += 1

            title = text.split(" Syndyk ")[0]
            title = title.split(" syndyk ")[0]
            title = clean_text(title)

            if len(title) < 20:
                title = text[:180]

            leads.append(build_lead(title, href, text))

        print(f"{page_url} -> znaleziono {found_on_page} leadów")

    return leads

def looks_like_title(line, next_text):
    line_clean = clean_text(line)
    lower = line_clean.lower()

    if not line_clean:
        return False

    if lower in BAD_TITLES:
        return False

    if len(line_clean) < 8 or len(line_clean) > 180:
        return False

    if line_clean.endswith("."):
        return False

    next_lower = next_text.lower()

    strong_title_words = [
        "lokal", "nieruchomość", "nieruchomosc",
        "ruchomości", "ruchomosci", "sprzęt", "sprzet",
        "domeny", "konkurs ofert", "wyposażenia",
        "wyposazenia", "piec", "samochód", "samochod"
    ]

    has_title_word = any(word in lower for word in strong_title_words)
    next_has_tender_words = any(word in next_lower for word in KEYWORDS)

    return has_title_word and next_has_tender_words

def extract_generic_text_page(source_url):
    soup = get_soup(source_url)

    for tag in soup(["script", "style", "nav", "footer"]):
        tag.decompose()

    text = soup.get_text("\n")
    lines = [clean_text(line) for line in text.split("\n")]
    lines = [line for line in lines if line]

    leads = []

    try:
        start_index = next(i for i, line in enumerate(lines) if line.lower() == "przetargi")
        lines = lines[start_index:]
    except StopIteration:
        pass

    current_title = None
    current_parts = []

    for i, line in enumerate(lines):
        next_text = " ".join(lines[i+1:i+8])

        if looks_like_title(line, next_text):
            if current_title and current_parts:
                description = clean_text(" ".join(current_parts))
                leads.append(
                    build_lead(
                        current_title,
                        make_fake_url(source_url, current_title),
                        description
                    )
                )

            current_title = line
            current_parts = []
        else:
            if current_title:
                current_parts.append(line)

    if current_title and current_parts:
        description = clean_text(" ".join(current_parts))
        leads.append(
            build_lead(
                current_title,
                make_fake_url(source_url, current_title),
                description
            )
        )

    unique = {}
    for lead in leads:
        unique[lead["url"]] = lead

    return list(unique.values())

def extract_leads_from_source(source_url):
    if "saltarski.com" in source_url:
        return extract_saltarski(source_url)

    return extract_generic_text_page(source_url)
