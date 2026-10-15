# -*- coding: utf-8 -*-
"""Δέχεται ο ζυγός T-Scale πεδία ΠΕΡΑ από τα 40 του ModelProduct;

Η εξαγωγή Excel του ζυγού έχει 63 στήλες (TASTE, STOCK, PRICE_VIP1-3, UNIT_TEXT,
DEFAULT_PCS, GROUP_QTY…), αλλά το AutoProcess στέλνει JSON με 40 κλειδιά. Δεν
ξέρουμε αν το POST /products δέχεται και τα υπόλοιπα. Αυτό το εργαλείο το
δοκιμάζει σε ΕΝΑ προϊόν, με ακίνδυνες τιμές, και ξαναδιαβάζει τον ζυγό:

    python dokimi_extra_pedia.py <IP ζυγού> <κωδικός προϊόντος>

Τι κάνει: GET /products → βρίσκει το προϊόν → το ξαναστέλνει ΙΔΙΟ, με επιπλέον
κλειδιά (stock=7, taste=1, unit_text=ΔΟΚ, price_vip1=1.11) → περιμένει 10 δευτ.
(όριο 429) → GET ξανά → λέει ποια από τα νέα κλειδιά γύρισαν πίσω με την τιμή
που στείλαμε. Ό,τι γυρίζει, το δέχεται ο ζυγός· ό,τι όχι, το αγνοεί.

Τρέξ' το σε ζυγό δοκιμής ή σε προϊόν που δεν πουλιέται — αλλάζει το stock του.
"""
import io
import json
import sys
import time
import urllib.request

PORT = 1235
# (κλειδί όπως υποθέτουμε ότι το λέει ο ζυγός, στήλη Excel, τιμή δοκιμής)
EXTRA = (("stock", "STOCK", "7"), ("stock_low", "STOCK_LOW", "1"), ("stock_top", "STOCK_TOP", "99"),
         ("taste", "TASTE", "1"), ("unit_text", "UNIT_TEXT", "ΔΟΚ"), ("default_pcs", "DEFAULT_PCS", "2"),
         ("price_vip1", "PRICE_VIP1", "1.11"), ("price_vip2", "PRICE_VIP2", "2.22"),
         ("price_vip3", "PRICE_VIP3", "3.33"), ("group_qty", "GROUP_QTY", "3"),
         ("group_price", "GROUP_PRICE", "9.99"), ("discount", "DISCOUNT", "5"),
         ("tare_num", "TARE_NUM", "1"), ("audio", "AUDIO", "1.wav"), ("trace", "TRACE", "1"),
         ("mark_num", "MARK_NUM", "1"), ("temp_index", "TEMP_INDEX", "1"), ("etag_id", "ETAG_ID", "1"),
         ("shop_id", "SHOP_ID", "1"), ("branch_id", "BRANCH_ID", "1"), ("pos_no", "POS_NO", "1"),
         ("changeprice", "CHANGEPRICE", "0"), ("fcl_ratio", "FCL_RATIO", "0"))


def get_products(ip):
    req = urllib.request.Request("http://%s:%d/products" % (ip, PORT),
                                 headers={"User-Agent": "RestSharp 102.7.0.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    ip, kodikos = sys.argv[1], sys.argv[2]
    data = get_products(ip)
    items = data if isinstance(data, list) else data.get("data") or data.get("products") or []
    proion = next((p for p in items if str(p.get("product_number")) == kodikos), None)
    if not proion:
        print("Δεν βρέθηκε προϊόν με product_number=%s (ο ζυγός έχει %d)" % (kodikos, len(items)))
        return 1
    print("Το προϊόν όπως το έχει ο ζυγός (%d κλειδιά):" % len(proion))
    print(json.dumps(proion, ensure_ascii=False)[:600])
    agnosta = [k for k in proion if k not in {kk for kk, _c, _v in EXTRA}]
    print("\nΚλειδιά που ΗΔΗ επιστρέφει ο ζυγός και δεν είναι στα 40: %s"
          % ", ".join(k for k in proion if k not in KNOWN40) or "—")
    neo = dict(proion)
    for key, _col, val in EXTRA:
        neo[key] = val
    body = json.dumps([neo], ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request("http://%s:%d/products" % (ip, PORT), data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "RestSharp 102.7.0.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        print("\nPOST → %s %s" % (r.status, r.read().decode("utf-8", "replace")[:200]))
    print("αναμονή 10 δευτ. (όριο 429)…")
    time.sleep(10)
    data2 = get_products(ip)
    items2 = data2 if isinstance(data2, list) else data2.get("data") or data2.get("products") or []
    meta = next((p for p in items2 if str(p.get("product_number")) == kodikos), {})
    print("\n%-14s %-14s %-8s %s" % ("ΚΛΕΙΔΙ", "EXCEL", "ΣΤΕΙΛΑΜΕ", "ΓΥΡΙΣΕ"))
    dexetai = []
    for key, col, val in EXTRA:
        back = meta.get(key, "(δεν υπάρχει)")
        ok = str(back) == val
        print("%-14s %-14s %-8s %s %s" % (key, col, val, back, "✓ ΔΕΧΕΤΑΙ" if ok else ""))
        if ok:
            dexetai.append(key)
    print("\nΔέχεται: %s" % (", ".join(dexetai) or "ΚΑΝΕΝΑ — ο ζυγός κρατά μόνο τα 40 γνωστά πεδία"))
    with io.open("dokimi_extra_pedia.json", "w", encoding="utf-8") as fh:
        json.dump({"prin": proion, "meta": meta, "dexetai": dexetai}, fh, ensure_ascii=False, indent=2)
    print("Λεπτομέρειες: dokimi_extra_pedia.json")
    return 0


KNOWN40 = {"product_number", "product_code", "product_name", "name_sort", "product_abbr", "abbr_sort",
           "category_num", "department_num", "pre_tare_value", "pre_tare_unit_index", "place_of_origin",
           "pcs_flag", "original_price", "sales_price", "price_unit_index", "tax_num", "barcode_format",
           "used_by_days", "reccommend_days", "label_format_num", "label_format_num2", "image_filename",
           "disabled", "shelf_num", "produced_date", "pack_date", "exp_date", "expiration_date",
           "ingredients", "temperature_info", "nutrition", "produced"} | {"remark_%d" % i for i in range(1, 9)}

if __name__ == "__main__":
    sys.exit(main())
