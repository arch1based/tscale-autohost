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

## ✅ ΕΠΙΒΕΒΑΙΩΜΕΝΟ — καταγραφή πραγματικού αιτήματος

Η **θύρα είναι 1235**, όχι 80. Βρέθηκε στον κώδικα της `HttpSend`
(`ldc.i4 0x4d3`) και επιβεβαιώθηκε με καταγραφή:

```
POST /products HTTP/1.1
Host: <IP ζυγού>:1235
Content-Type: application/json
Accept: application/json, application/xml, text/json, text/x-json, text/javascript, text/xml
User-Agent: RestSharp 102.7.0.0
Accept-Encoding: gzip, deflate
Connection: keep-alive
```

Η διεύθυνση χτίζεται ως `"http://" + IP + ":" + 1235 + "/products"`.

### Το σώμα: ΕΝΑΣ πίνακας με όλα τα προϊόντα

**1.146.229 bytes για 1393 προϊόντα** — δηλαδή όλα μαζί σε ένα αίτημα, όχι ένα-ένα,
χωρίς περιτύλιγμα:

```json
[
  { "product_number": "00010", "product_code": "00010",
    "product_name": "ΚΙΤΡΙΝΟΡΙΖΑ (ΚΟΥΡΚΟΥΜΑΣ) ΤΡΙΜΜA",
    "product_abbr": "ΚΙΤΡΙΝΟΡΙΖΑ (ΚΟΥΡΚΟΥΜΑΣ) ΤΡΙΜΜA",
    "original_price": "5.4", "price_unit_index": "0",
    "name_sort": null, "category_num": "", ... }
]
```

**Όλες οι τιμές είναι κείμενο** — και οι αριθμοί. Πεδία χωρίς αντιστοίχιση πάνε
είτε `""` είτε `null`, ποτέ δεν παραλείπονται.

### Πώς γεμίζουν από το CSV

| Στήλη CSV | Πεδίο JSON |
|---|---|
| ProductNumber | `product_number` **και** `product_code` |
| ProductName | `product_name` |
| Abbr | `product_abbr` |
| Price | `original_price` |
| Price Unit | `price_unit_index` |

### Προσοχή: κωδικοσελίδα

Στην καταγραφή τα ελληνικά ήρθαν **αλλοιωμένα** (`ÊÉÔÑÉÍÏÑÉÆÁ` αντί για ΚΙΤΡΙΝΟΡΙΖΑ):
το AutoProcess διάβασε το cp1253 αρχείο σαν Latin-1 και το έστειλε ως UTF-8.
Στο δικό μας πρόγραμμα θα διαβάζουμε σωστά και θα στέλνουμε καθαρό UTF-8 —
δηλαδή θα βγαίνουν **καλύτερα** από ό,τι σήμερα.

### Ροή σφαλμάτων

Το log ξεχωρίζει τα στάδια: `data success` (το CSV διαβάστηκε) και μετά
`Connection refused.` + `send fail` όταν δεν απαντά ο ζυγός. Άρα το «send fail»
χωρίς «data success» σημαίνει πρόβλημα **αρχείου**, όχι δικτύου.

## Τι μένει

Μόνο η **απάντηση του πραγματικού ζυγού** σε επιτυχία — ο ψεύτικος επέστρεψε
`{"result":"success"}` και το AutoProcess το δέχτηκε, αλλά καλό είναι να δούμε τι
στέλνει ο αληθινός για να ελέγχουμε σωστά την επιτυχία.
