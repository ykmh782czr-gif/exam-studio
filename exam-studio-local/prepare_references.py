"""Read-only analyst checks. Public prompts and private worked references stay separate."""
from pathlib import Path
import os
import collections
import csv
import datetime as dt
import hashlib
import json
import shutil
import sqlite3
import statistics
import xml.etree.ElementTree as ET
import zipfile
from excel_cases import build_excel_cases
from reference_library import signature

ROOT=Path(__file__).resolve().parent.parent
MATERIALS = Path(os.environ['EXAM_STUDIO_MATERIALS'])
PUBLIC=ROOT/'exam-studio-preview'


def remaining_film_references(shooting, solution_file):
    """Recalculate answers and check the course key, including boundary conventions."""
    def timestamp(row, field):
        return dt.datetime.strptime(row[field], '%m/%d/%Y %H:%M')

    borough_counts = collections.Counter()
    weekdays = collections.Counter()
    durations = []
    lead_times = []
    weekday_names = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
    friday_dates = friday_time = foreign = 0
    for row in shooting:
        start = timestamp(row, 'StartDateTime')
        end = timestamp(row, 'EndDateTime')
        entered = timestamp(row, 'EnteredOn')
        borough_counts[start.year, row['Borough']] += 1
        weekdays[weekday_names[start.weekday()]] += 1
        durations.append((end - start).total_seconds() / 60)
        lead_times.append((start - entered).total_seconds() / 86400)
        foreign += entered.year >= 2013 and row['Country'] != 'United States of America'
        friday = dt.datetime.combine(start.date(), dt.time()) + dt.timedelta(days=(4 - start.weekday()) % 7)
        saturday = friday + dt.timedelta(days=1)
        friday_dates += friday.date() <= end.date()
        friday_time += max(start, friday) < min(end, saturday)

    total = len(shooting)
    multiple = sum(',' in row['CommunityBoard(s)'] for row in shooting)
    manhattan = [row for row in shooting if row['Borough'] == 'Manhattan']
    broadway = sum('BROADWAY' in row['ParkingHeld'].upper() for row in manhattan)
    years = sorted({year for year, _ in borough_counts})
    overtakes = [year for year in years if borough_counts[year, 'Brooklyn'] > borough_counts[year, 'Manhattan']]
    first_year = overtakes[0]
    hours = statistics.mean(durations) / 60
    lead = statistics.mean(lead_times)
    weekday, weekday_count = weekdays.most_common(1)[0]
    calculated = {
        12: round(multiple / total, 4), 13: first_year, 14: round(broadway / len(manhattan), 2),
        15: foreign, 16: round(hours * 2) / 2, 17: min(durations), 18: round(lead),
        19: weekday, 20: round(friday_dates / total, 4),
    }
    with zipfile.ZipFile(solution_file) as workbook:
        strings = [''.join(t.text or '' for t in cell.findall('.//{*}t'))
                   for cell in ET.fromstring(workbook.read('xl/sharedStrings.xml'))]
        cells = {cell.get('r'): cell for cell in
                 ET.fromstring(workbook.read('xl/worksheets/sheet1.xml')).findall('.//{*}c')}
        for index, value in calculated.items():
            cell = cells[f'C{index + 2}']
            raw = cell.findtext('{*}v')
            expected = strings[int(raw)] if cell.get('t') == 's' else float(raw)
            if expected != value:
                raise ValueError(f'Film question {index}: calculated {value}, course key gives {expected}')

    references = [
        (12, f'{multiple / total:.2%}', [
            'Filter to Shooting Permit. A comma in CommunityBoard(s) separates multiple board codes.',
            f'Divide the {multiple:,} matching permits by all {total:,} shooting permits.']),
        (13, str(first_year), [
            'Use the year of StartDateTime. Count Shooting Permit records by year and borough in a PivotTable.',
            f'Brooklyn first exceeds Manhattan in {first_year} ({borough_counts[first_year, "Brooklyn"]:,} vs. {borough_counts[first_year, "Manhattan"]:,}).',
            f'The partial {years[-1]} data also show Brooklyn ahead ({borough_counts[years[-1], "Brooklyn"]:,} vs. {borough_counts[years[-1], "Manhattan"]:,}).']),
        (14, f'{calculated[14]:.0%}', [
            'Filter to Shooting Permit and Manhattan. Search ParkingHeld for BROADWAY.',
            f'Divide {broadway:,} matches by {len(manhattan):,} Manhattan shooting permits, then round to the nearest percent.',
            'The course answer uses a text match as a proxy for proximity. The data do not measure distance to Broadway.']),
        (15, str(foreign), [
            'Filter to Shooting Permit. Use EnteredOn on or after January 1, 2013, because the question concerns submission date.',
            'Count countries other than United States of America.']),
        (16, f'{calculated[16]:g} hours', [
            'Subtract StartDateTime from EndDateTime for each shooting permit and multiply the Excel day difference by 24.',
            f'Average the unrounded hours ({hours:.4f}), then use MROUND with a multiple of 0.5.']),
        (17, f'{min(durations):g} minute', [
            'For each shooting permit, multiply EndDateTime minus StartDateTime by 1440 to convert Excel days to minutes.',
            'Find the minimum and allow for floating-point rounding when displaying whole minutes.']),
        (18, f'{calculated[18]} days', [
            'Subtract EnteredOn from StartDateTime for each shooting permit. Keep fractional days and preserve signed values.',
            f'Average the day differences ({lead:.4f}), then round the result to the nearest whole day.']),
        (19, weekday, [
            'Group Shooting Permit records by the weekday of StartDateTime, for example using TEXT with the dddd format and a PivotTable.',
            f'{weekday} has the largest count at {weekday_count:,}.']),
        (20, f'{friday_dates / total:.2%} using the course key’s calendar-date convention', [
            'Filter to Shooting Permit. Find the first Friday on or after the start date and compare it with the end date.',
            f'The inclusive date comparison gives {friday_dates:,} of {total:,} permits, including permits ending at midnight as Friday begins.',
            f'Requiring a positive amount of time on Friday gives {friday_time:,} permits ({friday_time / total:.2%}). State which boundary rule you use.']),
    ]
    return references, {
        'solution_sha256': hashlib.sha256(solution_file.read_bytes()).hexdigest(),
        'course_key_matches': list(calculated),
        'shooting_permits': total,
        'brooklyn_ahead_years': overtakes,
        'friday_inclusive_count': friday_dates,
        'friday_positive_duration_count': friday_time,
    }


def main():
    questions=json.loads((PUBLIC/'questions.js').read_text().split('=',1)[1].strip().rstrip(';'))
    questions=[q for q in questions if not q['id'].startswith(('CHINOOK-','CS50-MOVIES-','REST-EXAM-','PCARD-','ETL-','INT-')) and q['id'] not in [f'CS50-SONGS-{i:03}' for i in range(4,9)]]
    pcard_folder=MATERIALS/'2. SQL part 2/Pcards Assignment'
    pcard_doc=pcard_folder/'Analytics_mindset_case_studies_PCard.docx'
    with zipfile.ZipFile(pcard_doc) as workbook:
        pcard_paragraphs=[''.join(t.text or '' for t in p.findall('.//{*}t')).strip()
                          for p in ET.fromstring(workbook.read('word/document.xml')).findall('.//{*}p')]
    pcard_specs=[
        (310,'Flag annual card spending over $50,000','Grouping and aggregation'),
        (314,'Flag monthly card spending over $10,000','Grouping and aggregation'),
        (318,'Find transactions over $5,000','Filtering and sorting'),
        (326,'Find possible split purchases at one vendor','Grouping and joins'),
    ]
    for i,(paragraph,title,skill) in enumerate(pcard_specs,1):
        questions.append({
            'id':f'PCARD-5-{i:02}','source_index':i,'title':title,'prompt':pcard_paragraphs[paragraph],
            'skill':skill,'tool':'SQL','category':'Data Manipulation','case':'P-Cards',
            'dataset':'pcards.db','source_file':pcard_doc.name,'source_section':f'Part V · Task 5 · Control {i}',
            'scope_note':'Use calendar year 2014. These results are flags for review. For the exercise, use FullName as the cardholder grouping field.',
            'output_requirement':'Return the fields and ordering requested in the prompt.',
        })
    shutil.copyfile(pcard_folder/'pcards.db',PUBLIC/'files/pcards.db')
    movies_folder=MATERIALS/'2. SQL part 1/Assignments/cs50 assignment/movies'
    movie_text=(movies_folder/'requierements.txt').read_text()
    movie_titles=['Find movies released in 2007','Find Johnny Depp’s birth year','Sort movies released since 2017','Count movies rated above 9','Find Toy Story movies','Average the ratings of 2013 movies','Rank rated movies from 2011','Find the cast of a Harry Potter film','List actors in 2003 movies','Find directors of highly rated movies','Rank Helena Bonham Carter’s movies','Find films with both actors','Find Kevin Bacon’s co-stars']
    movie_skills=['Filtering','Filtering','Sorting','Filtering and aggregation','Text matching','Joins and aggregation','Sorting','Joins','Joins and distinct values','Joins and distinct values','Sorting and limits','Combining conditions','Joins and distinct values']
    for i,(title,skill) in enumerate(zip(movie_titles,movie_skills),1):
        block=movie_text.split(f'In {i}.sql, ',1)[1]
        prompt=block.splitlines()[0]
        next_marker=f'In {i+1}.sql,'
        instruction_text=block.split(next_marker,1)[0].splitlines()[1:]
        instruction_text=[line.strip() for line in instruction_text if line.strip() and line.strip()!='After relational']
        questions.append({'id':f'CS50-MOVIES-{i:03}','source_index':i,'title':title,'prompt':prompt[0].upper()+prompt[1:],'skill':skill,'tool':'SQL','category':'Data Manipulation','case':'CS50 Movies','dataset':'movies.db','source_file':'movies/requierements.txt','source_section':f'{i}.sql','output_requirement':' '.join(instruction_text)})
    shutil.copyfile(movies_folder/'movies.db',PUBLIC/'files/movies.db')
    songs_folder=MATERIALS/'2. SQL part 1/Assignments/cs50 assignment/songs'
    songs_text=(songs_folder/'requierements.txt').read_text()
    songs_prompts={int(line.split('.sql')[0][3:]):line for line in songs_text.splitlines() if line.startswith('In ')}
    for index,title,skill in [(4,'Filter songs on three conditions','Combining conditions'),(5,'Calculate the average tempo','Aggregation'),(6,'Find songs by Drake','Joins'),(7,'Calculate Post Malone’s average energy','Joins and aggregation'),(8,'Find songs featuring other artists','Text matching')]:
        questions.append({'id':f'CS50-SONGS-{index:03}','source_index':index,'title':title,'prompt':songs_prompts[index],'skill':skill,'tool':'SQL','category':'Data Manipulation','case':'CS50 Songs','dataset':'songs.db','source_file':'songs/requierements.txt','source_section':('Before relational' if index<6 else 'After relational')+f' · {index}.sql','output_requirement':'Output one row and one column with the average.' if index in (5,7) else 'Output one column containing the song names.','scope_note':'Do not assume a fixed artist ID; find the artist by name.' if index in (6,7) else ('The source defines a featured artist by the literal text “feat.” in the song name.' if index==8 else '')})
    chinook_folder=MATERIALS/'2. SQL part 1/Assignments/pwc assignment'
    with zipfile.ZipFile(chinook_folder/'PWC SQL.docx') as z:
        ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        paragraphs=[''.join(n.text or '' for n in p.findall('.//w:t',ns)) for p in ET.fromstring(z.read('word/document.xml')).findall('.//w:p',ns)]
    indices=range(1,24)
    titles=['Inspect Customer columns','Find the fifth customer’s country','Sort customers by surname','Count invoices','Find invoices over $20','Find invoices between $10 and $20','Count invoices from three countries','Find billing countries beginning with C','Count customers with a company','Count employees','Remove phone area codes','Find the longest employee surname','Count Sunday birthdays','Find the oldest age at hire','Rank billing countries by invoice value','Count invoice line items','Count distinct unit prices','Count downloads by price','Find all most-downloaded tracks','Find the invoice date range','List five most-downloaded tracks','Count distinct complete albums','Find the most popular genre']
    skills=['Dataset structure','Sorting and limits','Sorting and limits','Aggregation','Filtering and aggregation','Combining conditions','Joins','Text matching','Missing data','Aggregation','Text extraction','Text length','Date analysis','Date analysis','Grouping and aggregation','Aggregation','Distinct values','Grouping and aggregation','Grouping and aggregation','Date analysis','Joins and aggregation','Joins and aggregation','Joins and aggregation']
    scopes={
        2:'Use Customer ordered by CustomerId ascending to make the first five rows reproducible.',
        3:'Use Customer and sort by LastName ascending, then CustomerId for ties.',
        7:'Use the customer’s Country, joining Invoice to Customer.',
        11:'Use Employee. Remove the parenthesized area code and retain the country prefix and local number.',
        12:'Use Employee, continuing the employee questions.',
        14:'Measure age from BirthDate to HireDate, in approximate years.',
        15:'Use Invoice.BillingCountry, following the supplied PWC answers document.',
        19:'Treat each InvoiceLine quantity as downloads. Return all tracks tied at the maximum.',
        21:'Treat each InvoiceLine quantity as downloads. Break ties by TrackId ascending to obtain a reproducible top five.',
        22:'A complete download requires every track of an album on one invoice. Count each qualifying AlbumId once across invoices.',
        23:'Define popularity as the highest total quantity downloaded.',
    }
    for i,title,skill in zip(indices,titles,skills):
        questions.append({'id':f'CHINOOK-{i:03}','source_index':i,'title':title,'prompt':paragraphs[i],'skill':skill,'tool':'SQL','category':'Data Manipulation','case':'PWC Chinook','dataset':'Chinook_Sqlite.sqlite','source_file':'pwc assignment/PWC SQL.docx','source_section':f'Question {i} · paragraph {i+1}','output_requirement':'Return the requested SQLite metadata or result table.','scope_note':scopes.get(i,'')})
    shutil.copyfile(chinook_folder/'Chinook_Sqlite.sqlite',PUBLIC/'files/Chinook_Sqlite.sqlite')
    by_id={q['id']:q for q in questions};references={};audit=[];contexts={}
    def reference(qid,answer,steps,method,source,**extra):
        references[qid]={'question_signature':signature(by_id[qid]),'answer':answer,'steps':steps,'verification':method,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'kind':'Analyst-checked worked reference; not an automatic grade',**extra}
    queries={
      'pcards.db':{
        'PCARD-5-01':'''SELECT FullName, ROUND(SUM(Amount), 2) AS TotalSpent
FROM pcards WHERE Year = 2014 GROUP BY FullName
HAVING SUM(Amount) > 50000 ORDER BY SUM(Amount) DESC, FullName;''',
        'PCARD-5-02':'''SELECT FullName, ROUND(SUM(Amount), 2) AS TotalSpent, Month
FROM pcards WHERE Year = 2014 GROUP BY FullName, Month
HAVING SUM(Amount) > 10000 ORDER BY Month, SUM(Amount) DESC, FullName;''',
        'PCARD-5-03':'''SELECT Amount, FullName, Description, Vendor, TransactionDate, PostedDate, MCC
FROM pcards WHERE Year = 2014 AND Amount > 5000
ORDER BY Amount DESC, TransactionDate, FullName;''',
        'PCARD-5-04':'''WITH flagged AS (
  SELECT FullName, Vendor, TransactionDate
  FROM pcards WHERE Year = 2014
  GROUP BY FullName, Vendor, TransactionDate
  HAVING COUNT(*) > 1 AND SUM(Amount) > 5000
)
SELECT p.* FROM pcards AS p JOIN flagged AS f
  ON p.FullName = f.FullName AND p.Vendor = f.Vendor AND p.TransactionDate = f.TransactionDate
WHERE p.Year = 2014
ORDER BY p.Month, CAST(SUBSTR(p.TransactionDate, INSTR(p.TransactionDate, '/') + 1) AS INTEGER),
  p.FullName, p.Vendor, p.Amount;''',
      },
      'songs.db':{
        'CS50-SONGS-001':'SELECT name, energy FROM songs;',
        'CS50-SONGS-002':'SELECT name FROM songs ORDER BY tempo DESC, name ASC;',
        'CS50-SONGS-003':'SELECT name FROM songs ORDER BY duration_ms DESC, name ASC LIMIT 3;',
        'CS50-SONGS-004':'SELECT name FROM songs WHERE danceability > 0.6 AND energy > 0.6 AND valence > 0.6;',
        'CS50-SONGS-005':'SELECT AVG(tempo) AS average_tempo FROM songs;',
        'CS50-SONGS-006':"SELECT songs.name FROM songs JOIN artists ON artists.id = songs.artist_id WHERE artists.name = 'Drake';",
        'CS50-SONGS-007':"SELECT AVG(songs.energy) AS average_energy FROM songs JOIN artists ON artists.id = songs.artist_id WHERE artists.name = 'Post Malone';",
        'CS50-SONGS-008':"SELECT name FROM songs WHERE name LIKE '%feat.%';"
      },
      'movies.db':{
        'CS50-MOVIES-001':'SELECT title FROM movies WHERE year = 2007;',
        'CS50-MOVIES-002':"SELECT birth FROM people WHERE name = 'Johnny Depp';",
        'CS50-MOVIES-003':'SELECT title FROM movies WHERE year >= 2017 ORDER BY title;',
        'CS50-MOVIES-004':'SELECT COUNT(DISTINCT movie_id) FROM ratings WHERE rating > 9.0;',
        'CS50-MOVIES-005':"SELECT title, year FROM movies WHERE title LIKE 'Toy Story%' ORDER BY year, title;",
        'CS50-MOVIES-006':'SELECT AVG(rating) FROM movies JOIN ratings ON movies.id = ratings.movie_id WHERE year = 2013;',
        'CS50-MOVIES-007':'SELECT title, rating FROM movies JOIN ratings ON movies.id = ratings.movie_id WHERE year = 2011 ORDER BY rating DESC, title;',
        'CS50-MOVIES-008':"SELECT people.name FROM people JOIN stars ON people.id = stars.person_id JOIN movies ON movies.id = stars.movie_id WHERE movies.title = 'Harry Potter and the Sorcerer''s Stone';",
        'CS50-MOVIES-009':'SELECT name FROM people WHERE id IN (SELECT person_id FROM stars JOIN movies ON movies.id = stars.movie_id WHERE year = 2003) ORDER BY birth, id;',
        'CS50-MOVIES-010':'SELECT name FROM people WHERE id IN (SELECT person_id FROM directors JOIN ratings USING (movie_id) WHERE rating >= 8.0);',
        'CS50-MOVIES-011':"SELECT title FROM movies JOIN ratings ON movies.id = ratings.movie_id WHERE movies.id IN (SELECT movie_id FROM stars JOIN people ON people.id = stars.person_id WHERE people.name = 'Helena Bonham Carter') ORDER BY rating DESC, title, movies.id LIMIT 5;",
        'CS50-MOVIES-012':"SELECT title FROM movies WHERE id IN (SELECT movie_id FROM stars JOIN people ON people.id = stars.person_id WHERE name = 'Johnny Depp' INTERSECT SELECT movie_id FROM stars JOIN people ON people.id = stars.person_id WHERE name = 'Helena Bonham Carter');",
        'CS50-MOVIES-013':"WITH kevin AS (SELECT id FROM people WHERE name = 'Kevin Bacon' AND birth = 1958) SELECT name FROM people WHERE id NOT IN (SELECT id FROM kevin) AND id IN (SELECT person_id FROM stars WHERE movie_id IN (SELECT movie_id FROM stars WHERE person_id IN (SELECT id FROM kevin)));",
      },
      'Chinook_Sqlite.sqlite':{
        'CHINOOK-001':'PRAGMA table_info(Customer);',
        'CHINOOK-002':'SELECT Country FROM Customer ORDER BY CustomerId LIMIT 1 OFFSET 4;',
        'CHINOOK-003':'SELECT LastName FROM Customer ORDER BY LastName, CustomerId LIMIT 1 OFFSET 2;',
        'CHINOOK-004':'SELECT COUNT(*) AS invoice_count FROM Invoice;',
        'CHINOOK-005':'SELECT COUNT(*) AS invoice_count FROM Invoice WHERE Total > 20;',
        'CHINOOK-006':'SELECT COUNT(*) AS invoice_count FROM Invoice WHERE Total > 10 AND Total < 20;',
        'CHINOOK-007':"SELECT COUNT(*) FROM Invoice JOIN Customer USING (CustomerId) WHERE Customer.Country IN ('Brazil','Argentina','Chile');",
        'CHINOOK-008':"SELECT COUNT(*) AS invoice_count FROM Invoice WHERE BillingCountry LIKE 'C%';",
        'CHINOOK-009':"SELECT COUNT(*) AS customer_count FROM Customer WHERE Company IS NOT NULL AND TRIM(Company) <> '';",
        'CHINOOK-010':'SELECT COUNT(*) FROM Employee;',
        'CHINOOK-011':"SELECT EmployeeId, RTRIM(SUBSTR(Phone, 1, INSTR(Phone, '(') - 1)) || ' ' || LTRIM(SUBSTR(Phone, INSTR(Phone, ')') + 1)) AS PhoneWithoutAreaCode FROM Employee ORDER BY EmployeeId;",
        'CHINOOK-012':'SELECT MAX(LENGTH(LastName)) FROM Employee;',
        'CHINOOK-013':"SELECT COUNT(*) FROM Employee WHERE STRFTIME('%w', BirthDate) = '0';",
        'CHINOOK-014':'SELECT ROUND(MAX((JULIANDAY(HireDate) - JULIANDAY(BirthDate)) / 365.2425), 2) AS ApproximateAge FROM Employee;',
        'CHINOOK-015':'SELECT BillingCountry, ROUND(SUM(Total), 2) AS CountryTotal FROM Invoice GROUP BY BillingCountry ORDER BY SUM(Total) DESC, BillingCountry ASC;',
        'CHINOOK-016':'SELECT COUNT(*) FROM InvoiceLine;',
        'CHINOOK-017':'SELECT COUNT(DISTINCT UnitPrice) FROM InvoiceLine;',
        'CHINOOK-018':'SELECT UnitPrice, SUM(Quantity) AS Downloads FROM InvoiceLine GROUP BY UnitPrice ORDER BY UnitPrice;',
        'CHINOOK-019':'''WITH downloads AS (
  SELECT TrackId, SUM(Quantity) AS DownloadCount FROM InvoiceLine GROUP BY TrackId
)
SELECT TrackId, Name, DownloadCount FROM downloads JOIN Track USING (TrackId)
WHERE DownloadCount = (SELECT MAX(DownloadCount) FROM downloads) ORDER BY TrackId;''',
        'CHINOOK-020':'SELECT MIN(DATE(InvoiceDate)) AS FirstDate, MAX(DATE(InvoiceDate)) AS LastDate FROM Invoice;',
        'CHINOOK-021':'''SELECT Track.Name, SUM(InvoiceLine.Quantity) AS Downloads
FROM Track JOIN InvoiceLine USING (TrackId)
GROUP BY Track.TrackId, Track.Name ORDER BY Downloads DESC, Track.TrackId LIMIT 5;''',
        'CHINOOK-022':'''WITH album_sizes AS (
  SELECT AlbumId, COUNT(*) AS TrackCount FROM Track GROUP BY AlbumId
), complete_purchases AS (
  SELECT InvoiceId, Track.AlbumId FROM InvoiceLine JOIN Track USING (TrackId)
  JOIN album_sizes ON album_sizes.AlbumId = Track.AlbumId
  GROUP BY InvoiceId, Track.AlbumId, album_sizes.TrackCount
  HAVING COUNT(DISTINCT Track.TrackId) = album_sizes.TrackCount
)
SELECT COUNT(DISTINCT AlbumId) FROM complete_purchases;''',
        'CHINOOK-023':'''SELECT Genre.Name, SUM(InvoiceLine.Quantity) AS Downloads
FROM InvoiceLine JOIN Track USING (TrackId) JOIN Genre USING (GenreId)
GROUP BY Genre.GenreId, Genre.Name ORDER BY Downloads DESC, Genre.GenreId LIMIT 1;''',
      }
    }
    for filename,items in queries.items():
        source={'songs.db':songs_folder,'movies.db':movies_folder,'Chinook_Sqlite.sqlite':chinook_folder,'pcards.db':pcard_folder}[filename]/filename
        connection=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);connection.execute('PRAGMA query_only=ON;')
        tables={name:[r[1] for r in connection.execute('PRAGMA table_info("'+name.replace('"','""')+'")')] for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        contexts[filename]={'dataset':filename,'dialect':'SQLite','tables':tables}
        for qid,sql in items.items():
            cursor=connection.execute(sql);rows=cursor.fetchall();columns=[v[0] for v in cursor.description]
            if qid=='CHINOOK-001':answer=f'{len(rows)} columns. The PRAGMA output has one row per column.'
            elif len(rows)==1 and len(columns)==1:answer=str(rows[0][0])
            else:answer=f'{len(rows)} result rows; columns: '+', '.join(columns)+'. Representative first rows are shown below.'
            limitations='Sample rows are illustrative, not a complete comparison table. Only requested ordering should be graded; equivalent SQL methods are acceptable.'
            if qid in ('CS50-SONGS-002','CS50-SONGS-003'):limitations+=' The name sort is a reproducible tie-breaker added by this reference, not a source requirement.'
            if qid=='CHINOOK-014': limitations+=' The key gives approximately 55.5 years. Using elapsed days divided by 365.2425 gives 55.62 years.'
            if qid=='CHINOOK-022': limitations+=' The supplied key lists 49. That matches counting complete invoice–album pairs, while counting distinct AlbumId values gives 41.'
            steps=['Use the named fields and scope in the question.','Run the reference query or an equivalent query, then inspect the requested columns, ordering and conditions.']
            samples=rows[:5]
            if filename=='pcards.db':
                answer=f'{len(rows):,} result rows. Run the query locally to inspect the flagged records.'
                steps=['Filter to 2014 before applying the spending rule.','For grouped checks, apply the threshold after summing the amounts. For the split-purchase check, join qualifying groups back to the transaction details.']
                limitations='A flag warrants further review. The query uses recorded net amounts and the name field as supplied. Named records are omitted from the worked reference.'
                samples=[]
            reference(qid,answer,steps, 'Reference SELECT/PRAGMA executed read-only against the supplied database.',source,query=sql,result_columns=columns,sample_rows=samples,limitations=limitations)
            audit.append({'question_id':qid,'rows':len(rows),'columns':columns,'source_sha256':references[qid]['source_sha256']})
        if filename=='Chinook_Sqlite.sqlite':
            expected={'CHINOOK-002':'Czech Republic','CHINOOK-003':'Bernard','CHINOOK-004':'412','CHINOOK-005':'4','CHINOOK-006':'60','CHINOOK-007':'49','CHINOOK-008':'77','CHINOOK-009':'10','CHINOOK-010':'8','CHINOOK-012':'8','CHINOOK-013':'2','CHINOOK-016':'2240','CHINOOK-017':'2','CHINOOK-022':'41'}
            assert all(references[qid]['answer']==answer for qid,answer in expected.items())
            pair_count = queries[filename]['CHINOOK-022'].replace('COUNT(DISTINCT AlbumId)', 'COUNT(*)')
            assert connection.execute(pair_count).fetchone()[0] == 49
            assert next(item for item in audit if item['question_id']=='CHINOOK-019')['rows'] == 256
            assert references['CHINOOK-023']['sample_rows'][0][0] == 'Rock'
        connection.close()
    film=MATERIALS/'1. Excel Part 1/PWC Excel Assignment/NYC_Film_Permits.txt'
    with film.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    shooting=[r for r in rows if r['EventType']=='Shooting Permit'];events=collections.Counter(r['EventType'] for r in rows);categories=collections.Counter(r['Category'] for r in shooting)
    invalid_zip=[r['ZipCode'] for r in rows if r['ZipCode']!='N/A' and (len(r['ZipCode'])!=5 or not r['ZipCode'].isdigit())]
    assert invalid_zip==['83','83']
    assert hashlib.sha256((chinook_folder/'Chinook_Sqlite.sqlite').read_bytes()).digest()==hashlib.sha256((PUBLIC/'files/Chinook_Sqlite.sqlite').read_bytes()).digest()
    constants=[key for key in rows[0] if len({r[key] for r in rows})==1]
    dates=[dt.datetime.strptime(r['EnteredOn'],'%m/%d/%Y %H:%M') for r in rows]
    film_refs=[(1,str(len(rows)),['Count the populated EventID data cells, excluding the header.','Check the used range before applying COUNTA; do not count an entire worksheet as records.']),(2,str(len(rows[0])),['Count the named header fields, not the Excel worksheet column limit.']),(3,str(sum(r['ZipCode']=='N/A' for r in rows)),['The supplied key treats literal text N/A as missing.','COUNTBLANK does not count the text N/A. Use COUNTIF on the actual ZIP-code data range with the criterion "N/A".','A full-column COUNTBLANK includes unused cells; a reported zero for that whole-column formula needs investigation.']),(4,str(len(invalid_zip)),['Exclude the N/A missing-value marker first.','For this exercise, treat a nonmissing ZIP code as valid only if it contains five digits. The two invalid entries are 83.']),(5,', '.join(constants),['Compare distinct values in each column across all records.']),(6,min(dates).strftime('%Y-%m-%d %H:%M'),['Interpret EnteredOn as month/day/year and time; take the minimum.','The source does not specify a timezone; do not invent a conversion.']),(7,max(dates).strftime('%Y-%m-%d %H:%M'),['Interpret EnteredOn as month/day/year and time; take the maximum.']),(8,str(len(events)),['Create a distinct list or PivotTable of EventType and count its unique categories.']),(9,events.most_common(1)[0][0],['Count records by EventType using all records.','For subsequent source questions, filter to Shooting Permit.']),(10,categories.most_common(1)[0][0],['Filter EventType to Shooting Permit.','Count by Category and identify the largest count.']),(11,str(sum(r['Category']=='Student' for r in shooting)),['Filter EventType to Shooting Permit and Category to Student.','Count the matching records; the same result can be obtained with COUNTIFS.'])]
    for i,answer,steps in film_refs:reference(f'PWC-EXCEL-{i:03}',answer,steps,'Independently calculated from the original comma-delimited TXT using Python; not executed in Excel.',film)
    assert [references[f'PWC-EXCEL-{i:03}']['answer'] for i in [1,2,3,5,8,11]]==['33502','14','11','EventAgency','4','193']
    remaining, film_audit = remaining_film_references(shooting, film.with_name('solutions.xlsx'))
    assert film.with_suffix('.xlsx').read_bytes() == (PUBLIC/'files/NYC_Film_Permits.xlsx').read_bytes()
    for index, answer, steps in remaining:
        reference(f'PWC-EXCEL-{index:03}', answer, steps,
                  'Calculated from the supplied TXT in Python and checked against the supplied Excel solutions.', film)
    regression_source=MATERIALS/'1. Excel part 4/Regression Assignment/Restaurant/data.xlsm'
    model=by_id['REST-REG-P']['model'];terms=[v['estimate'] for v in model['terms']];prediction=terms[0]+terms[1]*60+terms[2]*0
    reference('REST-REG-P',f'${prediction:,.2f}',['Set Temperature = 60°F and Game day = 0.',f'{terms[0]} + {terms[1]} × 60 + {terms[2]} × 0 = {prediction:.6f}.','Round only the final dollar amount to two decimal places.'], 'Arithmetic calculated from the displayed coefficients; source OLS checks are in restaurant-model-audit.json.',regression_source,numeric_check={'value':round(prediction,2),'unrounded':prediction,'absolute_tolerance':0.005},limitations='This checks the supplied model arithmetic, not the real-world accuracy of its forecast or the student’s workbook execution.')
    reference('REST-REG-S','About $7.58 greater predicted daily sales per additional 1°F; p ≈ 0.0077, significant at 5%.',['This is a simple model, not an adjustment for game days.','Describe an association in dollars per degree Fahrenheit, not causation.'], 'Reviewed against the calculated simple-model coefficients and p-value.',regression_source)
    reference('REST-REG-Q','The squared term has p ≈ 0.0105, so it is significant at 5% under the stated OLS assumptions.',['The fitted squared coefficient is negative, implying a concave temperature relationship within this model.','The marginal slope changes with temperature: b₁ + 2b₂ × Temperature.','This does not prove causation or that temperature always reduces sales.'], 'Reviewed against the calculated quadratic model.',regression_source)
    interaction=by_id['REST-REG-I']['model']['terms'];b=[term['estimate'] for term in interaction]
    reference('REST-REG-I',f'Non-game slope: {b[1]:.6f}; game-day slope: {b[1]+b[3]:.6f}.',['The intercept is predicted sales at earlier sales = 0 on a non-game day; consider whether that situation is within the data.',f'The game-day coefficient ({b[2]:.6f}) is the difference at earlier sales = 0, not a constant difference at every earlier-sales value.',f'The interaction changes the slope by {b[3]:.6f}; p ≈ {interaction[3]["p_value"]:.4f}, so there is no evidence of a slope difference at 5%.','Interpret coefficients as conditional associations, not causal effects.'], 'Reviewed against the calculated interaction model.',regression_source)
    variants=json.loads((ROOT/'exam-studio-local/restaurant-variants.json').read_text())
    assert variants['source_sha256']==hashlib.sha256(regression_source.read_bytes()).hexdigest()
    for variant in variants['exercises']:
        question=variant['question']
        questions.append(question)
        by_id[question['id']]=question
        reference(question['id'],variant['answer'],variant['steps'],
                  'Recalculated from displayed coefficients or model p-values. OLS fit to the supplied Restaurant workbook.',regression_source)
    excel_exercises, excel_contexts = build_excel_cases(MATERIALS, PUBLIC)
    contexts.update(excel_contexts)
    for question, source, answer, steps in excel_exercises:
        questions.append(question)
        by_id[question['id']] = question
        reference(question['id'], answer, steps, 'Calculated from the supplied course file in Python. Excel steps describe one reproducible method.', source,
                  additional_source_sha256={name: hashlib.sha256((PUBLIC/'files'/name).read_bytes()).hexdigest()
                                            for name in question.get('additional_datasets', [])})
    for q in questions:q['has_reference']=q['id'] in references
    (PUBLIC/'questions.js').write_text('window.EXAM_QUESTIONS = '+json.dumps(questions,ensure_ascii=False,indent=2)+';\n')
    (ROOT/'exam-studio-local/reference-solutions.json').write_text(json.dumps(references,ensure_ascii=False,indent=2))
    (ROOT/'exam-studio-local/dataset-contexts.json').write_text(json.dumps(contexts,ensure_ascii=False,indent=2))
    (ROOT/'exam-studio-discovery/reference-audit.json').write_text(json.dumps({'question_count':len(questions),'checked_references':len(references),'sql_checks':audit,'film_checks':film_audit,'regression_prediction':prediction,'sources_unchanged':True,'reference_policy':'References are private server-side material; only explicit requests outside an active simulation may reveal them.'},indent=2))
    print(json.dumps({'questions':len(questions),'checked_references':len(references),'SQL_exercises_executed':len(audit),'prediction':round(prediction,2)}))


if __name__=='__main__':main()
