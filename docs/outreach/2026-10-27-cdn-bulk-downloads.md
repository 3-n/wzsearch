# Letter: bulk downloads from cdn.um.warszawa.pl (draft, not sent)

Status: **draft for the owner**, 2026-10-27. Context: `BACKLOG.md` (city-wide draft, the CDN entry) and
`docs/plans/all-districts.md` §5a, owner decision 10.

**Why.** Since 27 Oct 2026 the city's file CDN (CloudFront in front of the district portals' documents) answers the
crawler with 403 for every file it does not have cached, even at one request per 10 s; cached files are served. The
same URL opens in a browser (checked by the owner on 27 Oct) – the links are not broken, automated clients are
refused. About 300 files are missing: Wesoła 158, Bielany 48, Białołęka 42, Włochy 40, Ursus 19. We do not work
around it (no other User-Agent, no other route, no browser "warming" of the cache); the crawler retries each run and
stops after three refusals in a row.

**Addressee.** The city portal's editorial team named on um.warszawa.pl/deklaracja-dostepnosci: Redakcja Serwisu
informacyjnego Urzędu m.st. Warszawy, `redakcja.piuw@um.warszawa.pl` (the CDN is shared by all district portals).
Alternative route, independent of this letter: ask the district offices for their registers as xlsx (decision 7).

**Before sending.** Decide what contact the crawler's User-Agent carries (today `wzSearch/0.1 (civic open-data
project)` in `pipeline/http.py` – no URL or e-mail); add it and quote the new string below. Fill in the signature.
The text avoids gendered first-person forms.

---

**Do:** redakcja.piuw@um.warszawa.pl
**Temat:** Pobieranie wykazów decyzji WZ/CP z cdn.um.warszawa.pl – prośba o wskazanie dozwolonego sposobu

Dzień dobry,

prowadzę niekomercyjny, obywatelski projekt wzSearch: przeglądarkę wykazów wniosków i decyzji o warunkach zabudowy
oraz o lokalizacji inwestycji celu publicznego, publikowanych przez urzędy dzielnic na podstawie zarządzenia
nr 1129/2020 Prezydenta m.st. Warszawy. Serwis pokazuje je na mapie, z odnośnikami do oryginalnych plików.

Raz w miesiącu program pobiera nowe pliki z wykazów dzielnic. Przedstawia się nagłówkiem User-Agent
„wzSearch/0.1 (civic open-data project)” i wysyła najwyżej jedno żądanie na 10 sekund. Każdy plik pobiera tylko raz,
a potem korzysta z własnej kopii.

27 października 2026 r. serwer cdn.um.warszawa.pl zaczął odpowiadać temu programowi błędem 403 na pliki, których nie
ma w pamięci podręcznej. Ten sam adres otwiera się bez problemu w przeglądarce, np.:
https://cdn.um.warszawa.pl/documents/45118/16484946/REJESTR+DECYZJI+WZ+05+2026+r.pdf/9b1482f6-9c52-74e9-986d-a3c87889038e?t=1781010644977
Dotyczy to około 300 plików z wykazów dzielnic Wesoła, Włochy, Ursus, Białołęka i Bielany. Nie próbowaliśmy obchodzić
tej blokady, np. podszywając się pod przeglądarkę.

Czy mogą Państwo:
1. dopuścić ruch z tym nagłówkiem User-Agent, w obecnym tempie lub w tempie, które Państwo wskażą, albo
2. wskazać inny akceptowany sposób pobierania tych plików, np. zbiorczą paczkę lub publikację na portalu otwartych
   danych?

Jeśli sprawa należy do innej komórki, proszę o przekazanie wiadomości lub wskazanie właściwego adresata.

Z poważaniem,
[imię i nazwisko]
[adres strony projektu, e-mail]
