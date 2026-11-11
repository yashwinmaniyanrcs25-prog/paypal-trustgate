"""Product Specification Normalization Layer for PayPal TrustGate.

Extracts, standardizes, and normalizes hardware specifications and marketplace
attributes from real-world provider payloads, titles, descriptions, and offers.
Does NOT fabricate missing information — missing or ambiguous attributes are set
to UNKNOWN / None to ensure deterministic fail-closed policy enforcement.
"""

import re
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class ProductSpecificationNormalizer:
    """Normalizes raw product metadata into verifiable structured specifications."""

    # Brand catalog
    KNOWN_BRANDS = [
        "Apple", "Lenovo", "Dell", "HP", "ASUS", "Acer", "MSI",
        "Samsung", "Microsoft", "Razer", "LG", "Keychron", "Logitech",
        "Google", "Sony", "Toshiba", "Alienware", "Framework"
    ]

    # Storage types
    STORAGE_TYPE_PATTERNS = [
        (re.compile(r"(?i)\b(?:nvme|pcie|m\.2)\s*ssd\b|\b(?:nvme|pcie)\b"), "NVMe SSD"),
        (re.compile(r"(?i)\b(?:ssd|solid\s+state\s+drive)\b"), "SSD"),
        (re.compile(r"(?i)\b(?:emmc|flash\s+storage)\b"), "eMMC"),
        (re.compile(r"(?i)\b(?:hdd|hard\s+disk|hard\s+drive)\b"), "HDD"),
    ]

    @classmethod
    def extract_brand_and_model(
        cls,
        title: str,
        description: str = "",
        raw_brand: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extracts brand and model from metadata, title, and description."""
        combined = f"{title} {description}"
        brand: Optional[str] = raw_brand.strip() if raw_brand and raw_brand.strip() else None

        if not brand:
            for b in cls.KNOWN_BRANDS:
                if re.search(rf"(?i)\b{re.escape(b)}\b", title):
                    brand = b
                    break

        # Model extraction heuristics
        model: Optional[str] = None
        model_patterns = [
            # HP (e.g. HP 15-dy2027od, Pavilion 14, Envy x360)
            r"(?i)\b(?:HP\s+)?(\d{1,2}-[a-z0-9]+)\b",
            r"(?i)\b(Pavilion\s+\d+|Envy\s+x?\d+|Spectre\s+x?\d+|Victus\s+\d+|Omen\s+\d+)\b",
            # Lenovo (e.g. IdeaPad Slim 3, ThinkPad E14, Legion 5, Yoga 7)
            r"(?i)\b(IdeaPad(?:\s+Slim)?\s+\d+|ThinkPad\s+[A-Z0-9]+|Legion\s+\d+|Yoga\s+\d+)\b",
            # Dell (e.g. XPS 13, XPS 15, Inspiron 15, Latitude 5420)
            r"(?i)\b(XPS\s+\d{2}|Inspiron\s+\d{2,4}|Latitude\s+\d{4}|G15\s+\d{4})\b",
            # ASUS (e.g. VivoBook Go 14, ZenBook 14, ROG Zephyrus)
            r"(?i)\b(VivoBook(?:\s+Go)?\s+\d+|ZenBook\s+\d+|TUF\s+Gaming|Zephyrus\s+[A-Z0-9]+)\b",
            # Apple (e.g. MacBook Air M1, MacBook Pro 16)
            r"(?i)\b(MacBook\s+(?:Air|Pro)(?:\s+[A-Z0-9]+)?)\b",
            # Acer (e.g. Aspire 5, Swift 3, Predator Helios)
            r"(?i)\b(Aspire\s+\d+|Swift\s+\d+|Nitro\s+\d+|Predator\s+\w+)\b",
            # Keychron (e.g. Keychron K2, K3, Q1)
            r"(?i)\b(Keychron\s+[A-Z0-9]+(?:\s+Pro)?)\b",
            # Logitech (e.g. MX Master 3S, MX Anywhere 3)
            r"(?i)\b(MX\s+Master\s+\d+[A-Z]?|MX\s+Anywhere\s+\d+[A-Z]?)\b",
        ]

        for pat in model_patterns:
            m = re.search(pat, combined)
            if m:
                model = m.group(1).strip()
                break

        return brand, model

    @classmethod
    def extract_ram_gb(cls, text: str, structured_ram: Any = None) -> Optional[int]:
        """Extracts RAM in GB from product text or structured attribute.
        
        Handles: '16GB RAM', '16 GB DDR5', '8GB Memory', '32GB LPDDR5', '8 GB', etc.
        Carefully avoids false-matching storage (e.g. '512GB SSD').
        """
        # Check structured attribute first if present
        if structured_ram:
            val_to_check = structured_ram[0] if isinstance(structured_ram, list) and structured_ram else structured_ram
            if isinstance(val_to_check, (int, float)):
                if 2 <= int(val_to_check) <= 256:
                    return int(val_to_check)
            elif isinstance(val_to_check, str):
                m = re.search(r"\b(\d{1,3})\s*(?:GB|G)?\b", val_to_check, re.IGNORECASE)
                if m:
                    try:
                        v = int(m.group(1))
                        if 2 <= v <= 256:
                            return v
                    except (ValueError, TypeError):
                        pass

        if not text:
            return None

        # Pattern 1: Explicit RAM keyword with capacity
        # e.g., '16GB RAM', '16 GB RAM', '8GB DDR4 RAM', '32GB Memory', '8GB Unified Memory', '16GB LPDDR4x Memory'
        explicit_pat = re.compile(
            r"(?i)\b(\d{1,3})\s*(?:GB|G)\s*(?:(?:DDR[345]X?|LPDDR[45]X?)\s*)?(?:RAM|Memory|System\s+Memory|Unified\s+Memory)\b"
        )
        match = explicit_pat.search(text)
        if match:
            try:
                val = int(match.group(1))
                if 2 <= val <= 256:
                    return val
            except (ValueError, TypeError):
                pass

        # Pattern 2: Secondary pattern e.g., 'RAM: 16GB' or 'Memory: 8 GB'
        prefix_pat = re.compile(
            r"(?i)\b(?:RAM|Memory|Installed\s+RAM)\s*[:=\-]?\s*(\d{1,3})\s*(?:GB|G)\b"
        )
        match = prefix_pat.search(text)
        if match:
            try:
                val = int(match.group(1))
                if 2 <= val <= 256:
                    return val
            except (ValueError, TypeError):
                pass

        # Pattern 3: Common spec bundle e.g. '16GB/512GB' or '8GB / 256GB SSD'
        bundle_pat = re.compile(r"(?i)\b(\d{1,3})\s*GB\s*/\s*(\d{1,4})\s*(?:GB|TB)\b")
        match = bundle_pat.search(text)
        if match:
            try:
                ram_val = int(match.group(1))
                if ram_val in (4, 8, 12, 16, 24, 32, 64):
                    return ram_val
            except (ValueError, TypeError):
                pass

        return None

    @classmethod
    def extract_storage(cls, text: str, structured_storage: Any = None) -> Tuple[Optional[int], Optional[str]]:
        """Extracts storage capacity in GB and storage type from text or structured attributes.
        
        Handles: '512GB SSD', '1TB NVMe SSD', '256GB PCIe M.2 SSD', '1TB HDD', '128GB eMMC'
        Converts TB to GB (1TB = 1024GB, 2TB = 2048GB).
        """
        # Detect storage type from text
        storage_type: Optional[str] = None
        if text:
            for pat, st_name in cls.STORAGE_TYPE_PATTERNS:
                if pat.search(text):
                    storage_type = st_name
                    break

        # Check structured storage
        if structured_storage:
            val_to_check = structured_storage[0] if isinstance(structured_storage, list) and structured_storage else structured_storage
            if isinstance(val_to_check, (int, float)):
                if int(val_to_check) >= 32:
                    return int(val_to_check), storage_type or "SSD"
            elif isinstance(val_to_check, str):
                s_str = val_to_check.strip()
                # Check TB
                tb_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:TB|Terabyte)", s_str, re.IGNORECASE)
                if tb_m:
                    try:
                        return int(round(float(tb_m.group(1)) * 1024)), storage_type or "SSD"
                    except (ValueError, TypeError):
                        pass
                # Check GB
                gb_m = re.search(r"(\d{2,4})\s*(?:GB)?", s_str, re.IGNORECASE)
                if gb_m:
                    try:
                        gb_v = int(gb_m.group(1))
                        if gb_v >= 32:
                            return gb_v, storage_type or "SSD"
                    except (ValueError, TypeError):
                        pass

        if not text:
            return None, None

        storage_gb: Optional[int] = None

        # Check for TB capacity first
        tb_pat = re.compile(
            r"(?i)\b(\d+(?:\.\d+)?)\s*(?:TB|Terabyte)\s*(?:NVMe|PCIe|M\.2|SSD|Solid\s+State\s+Drive|HDD|Hard\s+Drive|Storage)?\b"
        )
        tb_match = tb_pat.search(text)
        if tb_match:
            try:
                tb_val = float(tb_match.group(1))
                if 0.5 <= tb_val <= 16:
                    storage_gb = int(round(tb_val * 1024))
            except (ValueError, TypeError):
                pass

        # If not found in TB, check GB capacity
        if storage_gb is None:
            # Explicit storage pattern
            gb_pat = re.compile(
                r"(?i)\b(\d{2,4})\s*GB\s*(?:NVMe|PCIe|M\.2|SSD|Solid\s+State\s+Drive|eMMC|HDD|Hard\s+Drive|Storage|Flash\s+Storage)\b"
            )
            gb_match = gb_pat.search(text)
            if gb_match:
                try:
                    val = int(gb_match.group(1))
                    # Typical storage sizes: 64, 128, 256, 512, 1000, 1024, 2048
                    if val >= 32:
                        storage_gb = val
                except (ValueError, TypeError):
                    pass

        # Bundle pattern fallback e.g. '16GB/512GB'
        if storage_gb is None:
            bundle_pat = re.compile(r"(?i)\b\d{1,2}\s*GB\s*/\s*(\d{2,4})\s*GB\b")
            bundle_match = bundle_pat.search(text)
            if bundle_match:
                try:
                    val = int(bundle_match.group(1))
                    if val in (64, 128, 256, 512, 1024):
                        storage_gb = val
                        if not storage_type:
                            storage_type = "SSD"
                except (ValueError, TypeError):
                    pass

        # If storage_type not yet detected but storage was found with 'SSD' in text
        if storage_gb and not storage_type:
            if "ssd" in text.lower():
                storage_type = "SSD"

        return storage_gb, storage_type

    @classmethod
    def extract_processor(cls, text: str, structured_processor: Any = None) -> Optional[str]:
        """Extracts CPU / processor information.
        
        Handles: Intel Core i3/i5/i7/i9, Core Ultra, AMD Ryzen 3/5/7/9, Apple M1/M2/M3/M4,
        Intel Celeron, Pentium, Athlon.
        """
        if text:
            # Sanitize trademark symbols e.g. Intel® Core™ i5 -> Intel Core i5
            clean_text = text.replace("®", "").replace("™", "").replace("(R)", "").replace("(TM)", "")

            # Intel Core patterns
            m = re.search(r"(?i)\b(Intel\s+Core\s+(?:Ultra\s+)?[iI][3579](?:-[0-9A-Z]+|\s+\d+(?:th|nd|rd|st)\s+Gen)?)\b", clean_text)
            if m:
                return m.group(1).strip()

            # Intel short form: e.g. 'Core i5-1235U' or 'Core i7'
            m = re.search(r"(?i)\b(Core\s+[iI][3579](?:-[0-9A-Z]+)?)\b", clean_text)
            if m:
                return f"Intel {m.group(1).strip()}"

            # AMD Ryzen patterns
            m = re.search(r"(?i)\b(AMD\s+Ryzen\s+[3579](?:\s+[0-9A-Z]+)?)\b", clean_text)
            if m:
                return m.group(1).strip()

            # AMD short form: e.g. 'Ryzen 5 5500U'
            m = re.search(r"(?i)\b(Ryzen\s+[3579](?:\s+[0-9A-Z]+)?)\b", clean_text)
            if m:
                return f"AMD {m.group(1).strip()}"

            # Apple Silicon
            m = re.search(r"(?i)\b(Apple\s+M[1234](?:\s+(?:Pro|Max|Ultra))?)\b", clean_text)
            if m:
                return m.group(1).strip()
            m = re.search(r"(?i)\b(M[1234]\s+chip)\b", clean_text)
            if m:
                return "Apple " + m.group(1).replace(" chip", "").strip()

            # Low-end / Budget processors
            if re.search(r"(?i)\b(?:Intel\s+)?Celeron\b", clean_text):
                return "Intel Celeron"
            if re.search(r"(?i)\b(?:Intel\s+)?Pentium\b", clean_text):
                return "Intel Pentium"
            if re.search(r"(?i)\b(?:AMD\s+)?Athlon\b", clean_text):
                return "AMD Athlon"

        # Fallback to structured processor family if text had no match
        if structured_processor:
            val_to_check = structured_processor[0] if isinstance(structured_processor, list) and structured_processor else structured_processor
            if isinstance(val_to_check, str) and val_to_check.strip():
                p_cand = cls.extract_processor(val_to_check)
                if p_cand:
                    return p_cand
                return val_to_check.strip()

        return None

    @classmethod
    def extract_availability(
        cls,
        raw_avail: Optional[str] = None,
        text: str = "",
    ) -> str:
        """Determines availability status: 'InStock', 'OutOfStock', 'Discontinued', or 'Unknown'."""
        val = (raw_avail or "").strip().lower()
        t = text.lower()

        out_of_stock_cues = (
            "outofstock", "out of stock", "no longer available", "currently unavailable",
            "backorder", "sold out", "discontinued", "temporarily out of stock"
        )
        for cue in out_of_stock_cues:
            if cue in val or cue in t:
                return "OutOfStock"

        in_stock_cues = ("instock", "in stock", "available", "ships from", "in_stock", "ready to ship")
        for cue in in_stock_cues:
            if cue in val or cue in t:
                return "InStock"

        return "InStock" if raw_avail is None else "Unknown"

    @classmethod
    def extract_screen_size(cls, text: str) -> Optional[str]:
        """Extracts display size: e.g. 15.6 inch, 14 inch, 13.3 inch, 16 inch."""
        m = re.search(r"\b(1[1-7](?:\.[0-9])?)\s*(?:[\"″]|inch|-inch|in\b)", text, re.IGNORECASE)
        if m:
            return f"{m.group(1)} inch"
        return None

    @classmethod
    def normalize_specifications(
        cls,
        title: str,
        description: str = "",
        category: str = "General",
        raw_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Runs full normalization and returns structured specifications dictionary."""
        raw = raw_metadata or {}
        raw_kf = raw.get("key_features") or []
        kf_text = " ".join(str(k) for k in raw_kf if k) if isinstance(raw_kf, list) else ""
        combined_text = f"{title} {description} {kf_text} {str(raw)}"

        brand, model = cls.extract_brand_and_model(
            title=title,
            description=description,
            raw_brand=raw.get("brand") or raw.get("retailer") or raw.get("merchant_name"),
        )
        ram_gb = cls.extract_ram_gb(combined_text, structured_ram=raw.get("structured_ram"))
        storage_gb, storage_type = cls.extract_storage(combined_text, structured_storage=raw.get("structured_storage"))
        processor = cls.extract_processor(combined_text, structured_processor=raw.get("structured_processor"))
        screen_size = cls.extract_screen_size(combined_text)
        availability = cls.extract_availability(
            raw_avail=raw.get("availability"),
            text=combined_text,
        )

        # Verification status determination
        # For a laptop, RAM and Storage and Processor are key specs.
        is_laptop = "laptop" in category.lower() or "notebook" in category.lower() or "laptop" in title.lower()
        if is_laptop:
            if ram_gb is not None and storage_gb is not None:
                spec_status = "VERIFIED"
            elif ram_gb is None and storage_gb is None:
                spec_status = "UNKNOWN"
            else:
                spec_status = "UNVERIFIED"
        else:
            spec_status = "VERIFIED"

        return {
            "brand": brand,
            "model": model,
            "ram_gb": ram_gb,
            "storage_gb": storage_gb,
            "storage_type": storage_type,
            "processor": processor,
            "gpu": raw.get("gpu"),
            "screen_size": screen_size,
            "availability": availability,
            "spec_verification_status": spec_status,
        }


product_normalizer = ProductSpecificationNormalizer()
