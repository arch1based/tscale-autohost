# Πρωτόκολλο επικοινωνίας με τους ζυγούς T-Scale

Όσα βγήκαν από ανάλυση του `AutoProcess.exe` (.NET). Σκοπός: να στέλνουμε
**απευθείας από το πρόγραμμά μας**, χωρίς να ανοίγουμε το AutoProcess.

## Η ροή του AutoProcess

Οι μέθοδοι της κλάσης `ProductTool`, με τη σειρά που καλούνται:

```
timer1_Tick → SendData → SendToScale
                            ├── Ping(IP)          έλεγχος ότι απαντά ο ζυγός
                            ├── ReadyData()       CSV → αντικείμενα ModelProduct
                            ├── HttpSend()        POST http://<IP>/products
                            └── TCP_FileSend()    εικόνες/ετικέτες (ZipFile, TcpClient)
```

Στο log αντιστοιχούν: `data success` (πέρασε το ReadyData) και `send success` /
`send fail` (αποτέλεσμα του HttpSend).

**Σημαντικό:** κάνει **πρώτα ping**. Αν ο ζυγός δεν απαντά σε ICMP, δεν προσπαθεί καν
HTTP. Στο δικό μας πρόγραμμα καλό είναι να κάνουμε το ίδιο, για γρήγορο και σαφές
μήνυμα «ο ζυγός δεν απαντά» αντί για timeout.

## Το αίτημα

```
POST http://<IP ζυγού>/products
Content-Type: application/json
```

Βιβλιοθήκες: RestSharp (`RestClient`, `RestRequest`, `Method`, `Execute`,
`AddParameter`, `AddFile`) και Newtonsoft.Json (`JsonConvert.SerializeObject`).
Ελέγχει την απάντηση με `HttpStatusCode`.

Για εικόνες και ετικέτες υπάρχει δεύτερος δρόμος: `ZipFile` + `TcpClient` /
`NetworkStream` (διαδρομές `//BackUp//image_category`, `//Label`, `//BackUp//Slides`).

## Τα πεδία του JSON — κλάση `ModelProduct` (40 πεδία)

```
product_number      product_code        product_name        name_sort
product_abbr        abbr_sort           category_num        department_num
pre_tare_value      pre_tare_unit_index place_of_origin     pcs_flag
original_price      sales_price         price_unit_index    tax_num
barcode_format      used_by_days        reccommend_days     label_format_num
label_format_num2   image_filename      disabled            shelf_num
produced_date       pack_date           exp_date            expiration_date
ingredients         temperature_info    nutrition           produced
remark_1 … remark_8
```

*(το `reccommend_days` είναι όντως με δύο «c» στο πρωτότυπο)*

## Αντιστοίχιση στηλών CSV → πεδίων

Από τον πίνακα της κλάσης `ProductField`:

| Στήλη CSV | Πεδίο |
|---|---|
| ProductNumber | product_num |
| ProductName | product_name |
| NameSpell | name_spell |
| Price | price |
| Price Low | Price_Lowest |
| Pre tare | tare |
| BarCode | barcode |
| Abbreviation | abbr |
| Price Unit | priceunit |
| Category | category |
| Department | department |
| Origin | area |
| Label Format | labelFormat |
| Disabled | disabled |
| BarCode Format | barcode_format |
| Image | image · Audio → audio |
| Trace | trace · Mark Number → mark_num |
| Temperautre ID / Temperautre | temp_index / temp_text |
| Period | period · Recommend → recommend |
| Ingredient | ingredient · Produced → produced |
| Production / Packing / Use By date | KILL_DATA / PACKING_DATA / USED_DATA |
| Shop No / Branch Id / Scale No | shop_id / branch_id / pos_no |
| Stock / Stock Low / Stock Top | stock / stock_low / stock_top |
| Price VIP1-3 | price_vip1-3 |
| REMARK1-8 | remark1-8 |

## Τι λείπει ακόμα

1. **Η θύρα.** Το `ip.xml` δέχεται **μόνο σκέτη IP** — δοκιμάστηκε με `127.0.0.1:8080`
   και πέταξε `Could not resolve host`. Άρα η θύρα είναι σταθερή στον κώδικα,
   πιθανότατα **80**.
2. **Το σχήμα:** πίνακας προϊόντων σε ένα αίτημα, ή ένα-ένα; Και αν υπάρχει
   περιτύλιγμα (π.χ. `{"products": [...]}`).
3. **Η απάντηση επιτυχίας** του ζυγού.

Και τα τρία βγαίνουν με **μία** εκτέλεση του `fake_scale.py` σε μηχάνημα Windows,
όπως περιγράφει το `ODIGIES.md`.

## Γιατί δεν ολοκληρώθηκε σε Linux

Δοκιμάστηκε το AutoProcess μέσω wine, με ψεύτικο ζυγό στο 127.0.0.1 και έγκυρο
`product.csv` παραγωγής. Το πρόγραμμα έτρεξε και έφτασε στο `SendToScale`, αλλά
σκάει στο **Ping**: το wine δεν υλοποιεί το ICMP του .NET. Καταγράφει `send fail`
χωρίς καμία απόπειρα σύνδεσης — επιβεβαιώθηκε με ακρόαση σε 16 πιθανές θύρες.

Σε πραγματικά Windows το βήμα αυτό περνάει κανονικά.
