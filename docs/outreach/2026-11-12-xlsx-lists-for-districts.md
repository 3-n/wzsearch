# Letters: WZ/CP lists as spreadsheets – six PDF-only offices, Ursus, Żoliborz (drafts, not sent)

Status: **drafts for the owner**, 2026-11-12. Context: owner decision §7 #7 in `docs/plans/all-districts.md`
(write to the offices; the PDF reader stays either way). Addresses: each office's published general inbox
(`pipeline/districts.py` → `INBOXES`, with the page that publishes it).

**Why.** 11 of the 18 district offices publish their WZ/CP lists (zarządzenie nr 1129/2020) as Excel files from the
city's template. wzSearch reads those exactly, cell by cell. The six offices below publish only PDF. wzSearch reads
those PDFs from where the words sit on the page (`pipeline/pdftable.py`). That works, but:
- every change of print layout breaks it (Mokotów's report has had six layouts since 2021);
- text cut off at a printed cell's edge is lost for good (Ochota).

Ursus publishes Excel in its own layout, where the column headings don't match the contents and the applications
registers have no case numbers. Żoliborz's page has no list newer than January 2024.

**How to send.** One e-mail per office, from your own address. Fill in the signature (name, project address). Like
the CDN letter, the text avoids gendered first-person forms. Nothing in it depends on the CDN letter, which stays
unsent (decision §7 #10).

| Office | To | Publishes now | The ask (variant) |
|---|---|---|---|
| Białołęka | bialoleka.urzad@um.warszawa.pl | case-system report, PDF (cumulative files per year) | A |
| Bielany | bielany.urzad@um.warszawa.pl | case-system report, PDF | A |
| Mokotów | mokotow.urzad@um.warszawa.pl | case-system report, PDF; six print layouts since 2021 | A + Mokotów sentence |
| Ochota | ochota.wom@um.warszawa.pl | city template printed to PDF; long cells cut off at the cell edge | B + Ochota sentence |
| Targówek | targowek.urzad@um.warszawa.pl | city template printed to PDF | B |
| Włochy | sekretariat.udwlochy@um.warszawa.pl | city template printed to PDF (some rows without Lp.) | B |
| Ursus | ursus.urzad@um.warszawa.pl | own Excel registers (headings ≠ contents; applications without case numbers) | C |
| Żoliborz | zoliborz.urzad@um.warszawa.pl | Excel from the city template; newest list on the page: January 2024 | D |

---

**Temat:** Wykazy wniosków i decyzji WZ/CP – prośba o publikację także w formacie Excel

Dzień dobry,

prowadzę niekomercyjny, obywatelski projekt wzSearch. To bezpłatna przeglądarka wykazów wniosków i decyzji
o warunkach zabudowy oraz o lokalizacji inwestycji celu publicznego, publikowanych przez urzędy dzielnic na podstawie
zarządzenia nr 1129/2020 Prezydenta m.st. Warszawy. Serwis zbiera wykazy wszystkich 18 dzielnic. Pokazuje je na
mapie, pozwala je przeszukiwać, a przy każdej pozycji podaje odnośnik do oryginalnego pliku urzędu.

*[wariant A – Białołęka, Bielany, Mokotów]*
Urząd Dzielnicy [nazwa] publikuje wykazy jako raport PDF z systemu obsługi spraw. Odczytujemy go z układu tekstu na
stronie, więc każda zmiana szablonu wydruku może spowodować błędy w danych.
*[tylko Mokotów:]* Od 2021 r. układ tego raportu zmieniał się sześć razy.

*[wariant B – Ochota, Targówek, Włochy]*
Urząd Dzielnicy [nazwa] publikuje wykazy jako PDF wydrukowany z arkusza według wzoru miejskiego. Odczytujemy je
z układu tekstu na stronie, więc każda zmiana szablonu wydruku może spowodować błędy w danych.
*[tylko Ochota:]* Dłuższe opisy, np. adresy z kilkoma działkami, są w wydruku ucięte na granicy komórki. Tej części
treści nie da się odczytać z PDF.

Czy byłoby możliwe publikowanie tych samych wykazów także w formacie Excel (.xlsx), obok plików PDF? Najwygodniejszy
byłby plik według wzoru miejskiego. Tak publikuje 11 innych dzielnic, np. Bemowo, Praga-Południe czy Wawer.
Dane i zakres informacji pozostałyby bez zmian, a skorzystaliby na tym wszyscy, którzy chcą je przeszukiwać lub
analizować.

*[wariant C – Ursus]*
Urząd Dzielnicy Ursus publikuje wykazy w formacie Excel, za co dziękuję. Mają one jednak układ inny niż wzór
miejski. W części arkuszy nagłówki kolumn nie odpowiadają ich zawartości. Rejestry wniosków nie podają numeru sprawy,
więc trudno je powiązać z późniejszą decyzją. Czy byłoby możliwe publikowanie wykazów według wzoru miejskiego, tak
jak robi to 11 innych dzielnic, np. Bemowo, Praga-Południe czy Wawer? Pomocne byłoby też podawanie numeru sprawy
w rejestrze wniosków.

*[wariant D – Żoliborz]*
Na stronie Urzędu Dzielnicy Żoliborz
(https://zoliborz.um.warszawa.pl/-/informacja-o-wszczetych-postepowaniach-oraz-wydanych-decyzjach-administracyjnych-1)
najnowszy wykaz obejmuje styczeń 2024 r. Czy wykazy za kolejne miesiące są publikowane w innym miejscu? Jeśli nie,
czy planowane jest ich uzupełnienie?

Jeśli sprawa należy do innej komórki, proszę o przekazanie wiadomości lub wskazanie właściwego adresata.

Z poważaniem,
[imię i nazwisko]
[adres strony projektu, e-mail]
