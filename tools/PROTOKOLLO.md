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


## Ποιες στήλες στέλνονται

Το πρόγραμμά μας αναγνωρίζει **40 στήλες** και τις στέλνει στο αντίστοιχο πεδίο του
ζυγού. Οι πρώτες 13 είναι όσες έστελνε και το AutoProcess· οι υπόλοιπες υπάρχουν στον
ζυγό αλλά **δεν τις έστελνε ποτέ** — τώρα μπορούμε.

| Στήλη CSV | Πεδίο ζυγού | |
|---|---|---|
| ProductNumber | product_number | και AutoProcess |
| BarCode | product_code | και AutoProcess |
| ProductName | product_name | και AutoProcess |
| Abbr | product_abbr | και AutoProcess |
| Price | original_price | και AutoProcess |
| Price Low | sales_price | και AutoProcess |
| Price Unit | price_unit_index | και AutoProcess |
| Category | category_num | και AutoProcess |
| Department | department_num | και AutoProcess |
| Pre tare | pre_tare_value | και AutoProcess |
| BarCode Format | barcode_format | και AutoProcess |
| Label Format | label_format_num | και AutoProcess |
| Disabled | disabled | και AutoProcess |
| NameSpell | name_sort | **νέο** |
| AbbrSpell | abbr_sort | **νέο** |
| Origin | place_of_origin | **νέο** |
| Ingredient | ingredients | **νέο** |
| Nutritional | nutrition | **νέο** |
| Temperautre | temperature_info | **νέο** |
| Period | used_by_days | **νέο** |
| Recommend | reccommend_days | **νέο** |
| Production date | produced_date | **νέο** |
| Packing date | pack_date | **νέο** |
| Use By date | exp_date | **νέο** |
| Image | image_filename | **νέο** |
| Shelf Number | shelf_num | **νέο** |
| Tax | tax_num | **νέο** |
| Pcs | pcs_flag | **νέο** |
| Produced | produced | **νέο** |
| REMARK1 … REMARK8 | remark_1 … remark_8 | **νέο** |

Στήλη που δεν υπάρχει στον πίνακα **αγνοείται** — το log το γράφει ρητά, ώστε να μη
νομίζουμε ότι στάλθηκε κάτι που δεν στάλθηκε.

Το JSON περιέχει **πάντα και τα 40 πεδία**· όσα δεν γεμίζουν πάνε `""` ή `null`,
ακριβώς όπως τα στέλνει το AutoProcess.


## ✅ Επαλήθευση: το αίτημά μας είναι πανομοιότυπο

Στάλθηκε το ίδιο `product.csv` (1393 προϊόντα) πρώτα από το AutoProcess και μετά από
το πρόγραμμά μας, με καταγραφή του ακατέργαστου σώματος:

```
AutoProcess : 1.146.229 bytes
δικό μας    : 1.146.229 bytes
ταυτόσημα byte-προς-byte: ΝΑΙ
```

Χρειάστηκαν τέσσερις λεπτομέρειες για να πέσει ακριβώς πάνω:

1. **JSON χωρίς κενά** μετά από `:` και `,` (έτσι γράφει το Newtonsoft.Json).
2. **Τα διπλά εισαγωγικά αφαιρούνται** από τις τιμές: `ΣΑΛΑΜΙ "ΩΡΑΙΑ ΔΡΑΜΑ"` γίνεται
   `ΣΑΛΑΜΙ ΩΡΑΙΑ ΔΡΑΜΑ`.
3. **Τα κενά στο τέλος μένουν** — δεν κόβονται.
4. **Κωδικοσελίδα:** το AutoProcess διαβάζει το cp1253 αρχείο σαν **Windows-1252**.
   Το «Κ» (0xCA) γίνεται «Ê», αλλά το «’» (0x92) περνάει σωστά — αυτό ακριβώς
   αποκλείει το Latin-1 και επιβεβαιώνει το cp1252.

## Καμία ταυτοποίηση

Στην καταγραφή **δεν υπάρχει κανένα στοιχείο πιστοποίησης**: ούτε `Authorization`,
ούτε token, ούτε cookie, ούτε κλειδί μέσα στο JSON. Ούτε προηγείται κάποιο αίτημα
σύνδεσης — ο ψεύτικος ζυγός δέχτηκε **ένα και μόνο** αίτημα, το `POST /products`.

Οι κεφαλίδες που στέλνουμε είναι οι ίδιες, μαζί με το `User-Agent: RestSharp 102.7.0.0`,
ώστε ο ζυγός να μη βλέπει καμία διαφορά.
