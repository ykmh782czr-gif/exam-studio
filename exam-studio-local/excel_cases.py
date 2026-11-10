"""Course inputs and independently calculated references for ETL and IntegrateCo."""

import csv
from decimal import Decimal
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile


EXCEL_CASE_FILES = {
    'ETL-Case1.csv': 'Analytics_mindset_case_studies_ETL_Case1.csv',
    'ETL-Case2.xlsx': 'Analytics_mindset_case_studies_ETL_Case2_Excel.xlsx',
    'ETL-Case3.xlsx': 'Analytics_mindset_case_studies_ETL_Case3_Excel.xlsx',
    'ETL-Case4.xlsx': 'Analytics_mindset_case_studies_ETL_Case4_Excel.xlsx',
    'IntegrateCo-2015.csv': 'Analytics_mindset_case_studies_IntegrateCo_2015payroll.csv',
    'IntegrateCo-2016.csv': 'Analytics_mindset_case_studies_IntegrateCo_2016payroll.csv',
}


def workbook_rows(path, sheet):
    with zipfile.ZipFile(path) as book:
        strings = [''.join(t.text or '' for t in item.findall('.//{*}t'))
                   for item in ET.fromstring(book.read('xl/sharedStrings.xml'))]
        table = ET.fromstring(book.read(f'xl/worksheets/sheet{sheet}.xml'))
    result = []
    for row in table.findall('./{*}sheetData/{*}row'):
        cells = {}
        for cell in row.findall('{*}c'):
            value = cell.findtext('{*}v')
            if value is not None:
                column = re.sub(r'\d+', '', cell.get('r'))
                cells[column] = strings[int(value)] if cell.get('t') == 's' else value
        if cells:
            result.append(cells)
    return result


def payroll_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as source:
        records = list(csv.DictReader(source, delimiter='|'))
    assert records and all(None not in row and None not in row.values() for row in records)
    return records


def build_excel_cases(materials, public):
    sources = {alias: next(materials.rglob(filename)) for alias, filename in EXCEL_CASE_FILES.items()}
    for alias, path in sources.items():
        shutil.copyfile(path, public/'files'/alias)
    exercises = []
    contexts = {}

    def add(qid, dataset, section, title, skill, prompt, scope, answer, steps, other=()):
        case = 'ETL' if qid.startswith('ETL-') else 'IntegrateCo'
        brief = ('Analytics_mindset_case_studies_ETL.docx' if case == 'ETL'
                 else 'Analytics_mindset_case_studies_IntegrateCo_Excel.docx')
        question = dict(id=qid, title=title, skill=skill, prompt=prompt, scope_note=scope,
                        dataset=dataset, tool='Excel', category='Data Manipulation', case=case,
                        source_file=brief, source_section=section,
                        adaptation='Short practice exercise adapted from the named course brief.',
                        output_requirement='Show the Excel steps or formula and the requested result.')
        if other:
            question['additional_datasets'] = list(other)
        exercises.append((question, sources[dataset], answer, steps))

    # The original CSV has unquoted commas in some names but quotes numeric thousands.
    with sources['ETL-Case1.csv'].open(encoding='utf-8-sig', newline='') as source:
        raw = list(csv.reader(source))
    header, records = raw[0], raw[1:]
    apple = next(row for row in records if row[0]=='AAPL' and '2018' in row)
    year_index = apple.index('2018')
    assert apple[year_index+1].endswith(' M')
    cash = Decimal(apple[year_index+1].removesuffix(' M')) * 1_000_000
    malformed = sum(len(row)!=len(header) for row in records)
    contexts['ETL-Case1.csv'] = {'columns':header,'notes':'Preserve CSV quotes. Some company names contain unquoted commas, causing an extra field.'}
    add('ETL-01','ETL-Case1.csv','Case 1 · Required, data import','Diagnose shifted CSV columns','CSV import',
        'Compare the header with the imported data. How many records have a different field count? Use an affected row to explain the cause and how to fix the import.',
        'Treat a quoted number containing commas as one field. Exclude the header from the count.',
        f'{malformed} records have a field count different from the {len(header)}-field header.',
        ['Use comma as the separator and double quotes as the text qualifier. Inspect rows where the year lands outside the Year field.',
         'Apple, Inc. is unquoted in the source. Its comma splits the name. Quote the full name in a working copy and verify that the year returns to the Year column.'])
    add('ETL-02','ETL-Case1.csv','Case 1 · Required, transform the data','Convert cash recorded in millions','Numeric conversion',
        'After aligning the CSV fields, convert Apple’s 2018 Cash value to a number in dollars. Show how you treat the unit suffix.',
        'Use the row with ticker AAPL and year 2018. M means millions.',
        f'${cash:,.0f}', ['Remove the M suffix and surrounding spaces, convert the remaining digits to a number, then multiply by 1,000,000.'])

    for case, pattern in [(2,r'([A-Za-z]+)(\d+)-(\d+)([WM])'),(3,r'([A-Za-z]+)(\d+)-(\d+)(We|Mo|W|M)')]:
        dataset=f'ETL-Case{case}.xlsx'
        table=workbook_rows(sources[dataset],1)
        codes=[row['A'] for row in table[1:]]
        matches=[re.fullmatch(pattern,code) for code in codes]
        assert len(codes)==597 and all(matches)
        location, employee, plant, pay=matches[0].groups()
        contexts[dataset]={'columns':['EmployeeCode','FirstName','LastName'],'worksheet':'Case 2' if case==2 else 'Case 3 data','notes':'Plant and employee IDs are text identifiers. Keep the original codes.'}
        offset=3 if case==2 else 5
        add(f'ETL-{offset:02}',dataset,f'Case {case} · Required, extract fields',
            'Extract fields from a fixed-width code' if case==2 else 'Extract fields from a variable-width code','Text extraction',
            'Use formulas to split the EmployeeCode in A2 into Location, EmpID, PlantID and PayPeriod. Show the resulting four values.',
            f'Use the {contexts[dataset]["worksheet"]} worksheet. PayPeriod should retain the suffix exactly as written.',
            f'Location: {location}. EmpID: {employee}. PlantID: {plant}. PayPeriod: {pay}.',
            ['Use LEFT for the three-letter location, MID for the four employee digits, two digits after the hyphen for the plant, and RIGHT for the final character.' if case==2 else
             'Find the first digit to separate Location from EmpID. Use the hyphen to split EmpID from PlantID, then find the first letter after the hyphen to separate PlantID from PayPeriod.',
             'Keep the extracted identifiers as text.'])
        if case==2:
            count=len({(m[1],m[3]) for m in matches})
            add('ETL-04',dataset,'Case 2 · Required, LocationPlantID','Build a unique plant key','Composite identifiers',
                'Create LocationPlantID in the format Location-PlantID. Give the key for A2 and the number of distinct keys across the worksheet.',
                'Use all 597 data rows. Keep the hyphen and preserve plant codes.',
                f'{location}-{plant} for A2. There are {count} distinct location–plant keys.',
                ['Concatenate the extracted fields with Location & "-" & PlantID. Count the rows returned by UNIQUE on the resulting data column.'])
        else:
            weekly=sum(m[4] in ('W','We') for m in matches)
            add('ETL-06',dataset,'Case 3 · Required, variable-width extraction','Standardize pay period labels','Category cleaning',
                'Extract and standardize the pay period suffix for every employee. How many records are weekly and how many are monthly?',
                'Treat W and We as weekly, and M and Mo as monthly.',
                f'Weekly: {weekly}. Monthly: {len(codes)-weekly}.',
                ['Extract the suffix after the last plant digit. Map W or We to Weekly and M or Mo to Monthly, then count each group with COUNTIF.'])

    journal='ETL-Case4.xlsx'
    first_line=workbook_rows(sources[journal],1)[1]
    accounts={r['B']:r for r in workbook_rows(sources[journal],3)[1:] if 'B' in r}
    account=accounts[first_line['B']]
    preparers=workbook_rows(sources[journal],4)[1:]
    pair=(first_line['D'],first_line['C'])
    matches=[r for r in preparers if (r.get('B'),r.get('C'))==pair]
    assert len(matches)==1 and sum(r.get('B')==pair[0] for r in preparers)>1
    preparer=matches[0]['A'].split('|',1)[0].strip()
    contexts[journal]={'worksheets':['JELineItems','BusinessUnits','ChartOfAccounts','PreparerInfo','Source','Case 4 solution'],'notes':'ChartOfAccounts has the account name left of the account-number key. PreparerInfo requires PreparerID and BusinessUnitID together.'}
    add('ETL-07',journal,'Case 4 · Required, enrich journal lines','Look up a GL account by number','Lookup formulas',
        'For the first journal line, use its GLAccountNumber to look up GLAccountName and AccountType. Show a formula that can be filled down.',
        'Use row 2 of JELineItems and match against ChartOfAccounts.',
        f'{account["A"].strip()} ({account["C"]}).',
        ['For the name use =INDEX(ChartOfAccounts!A$2:A$86,MATCH(B2,ChartOfAccounts!B$2:B$86,0)) in the solution sheet.',
         'For AccountType, return column C instead. The match is exact and can return a column to the left of the key.'])
    add('ETL-08',journal,'Case 4 · Required, preparer lookup','Match a preparer using two fields','Composite lookup',
        'Find the preparer name for the first journal line and explain why matching only on PreparerID is insufficient.',
        'Use row 2 of JELineItems. Return the name before the pipe in PreparerInfo.',
        f'{preparer}. PreparerID {pair[0]} occurs in multiple business units.',
        ['Match PreparerID and BusinessUnitID together, for example using XLOOKUP on a two-condition Boolean product.',
         'Split the returned PreparerName field at the pipe and trim the name.'])

    prior='IntegrateCo-2015.csv'
    current='IntegrateCo-2016.csv'
    old,new=(payroll_rows(sources[key]) for key in (prior,current))
    for key, data in ((prior,old),(current,new)):
        contexts[key]={'columns':list(data[0]),'delimiter':'|','notes':'Six months of payroll data. Keep employee numbers and job codes as text when importing.'}
    missing=[row for row in new if not row['Employee_Number'].strip()]
    missing_pay=sum(Decimal(row['Gross_Wages']) for row in missing)
    employer_columns=('Gross_Wages','SocSec_Medicare','FUTA','SUTA','Work_Comp')
    total=sum(Decimal(row[col]) for row in new for col in employer_columns)
    old_gross=sum(Decimal(row[col]) for row in old for col in ('Reg_Pay','OT_Pay'))
    new_gross=sum(Decimal(row['Gross_Wages']) for row in new)
    add('INT-01',prior,'Part 2 · Import and transform','Import pipe-delimited payroll','Delimited import',
        'Import the 2015 payroll file into Excel. Which delimiter should you select, and how many rows and fields should the imported table contain?',
        'Count data rows separately from the header.',
        f'Pipe (|). {len(old):,} data rows and {len(old[0])} columns.',
        ['Use Excel’s text/CSV import and select the pipe as the delimiter. Keep Emp_No and Job as text, then check the resulting dimensions.'])
    add('INT-02',prior,'Part 2 · Harmonize the two systems','Extract the job code after an optional department','Text extraction',
        'The brief gives 14005 and 15S002 as examples of the Job field. Extract the three-digit job code for each and explain how to handle the optional department letter.',
        'The first two characters indicate the project year. Preserve leading zeros in job codes.',
        '14005 → 005. 15S002 → 002.',
        ['Check character 3 for H or S. Use MID from position 4 if it is a department letter, or position 3 otherwise, taking three characters.',
         'Validate extracted values against job codes 001 through 012. A parsable field can still contain an invalid job code.'])
    add('INT-03',current,'Part 4 · Missing employee numbers','Find payroll entries without an employee number','Missing data',
        'How many 2016 rows lack Employee_Number, and what is their total Gross_Wages?',
        'Treat a blank or whitespace-only Employee_Number as missing. Keep these rows in the calculation.',
        f'{len(missing)} rows. Gross wages: ${missing_pay:,.2f}.',
        ['Create a missing-number flag with LEN(TRIM(...))=0. Count flagged rows and sum Gross_Wages for the same flag.'])
    add('INT-04',current,'Part 4 · Total employee cost','Calculate total employee cost','Summation',
        'Calculate the total employee cost in 2016 across all projects, including the five cost fields specified in the brief.',
        'Include every row and the columns Gross_Wages, SocSec_Medicare, FUTA, SUTA and Work_Comp.',
        f'${total:,.2f}.',
        ['Sum the five columns across the full imported table. Include rows with a missing employee number because the question asks for total cost.'])
    add('INT-05',prior,'Part 2 and Part 3 · Compare years','Reconcile gross wages across payroll systems','Harmonization',
        'Use both payroll files to calculate gross wages for each year and the change from 2015 to 2016.',
        'Use all rows in both files. Compare the same six-month periods and report 2016 minus 2015.',
        f'2015: ${old_gross:,.2f}. 2016: ${new_gross:,.2f}. Change: ${new_gross-old_gross:,.2f}.',
        ['For 2015 add Reg_Pay and OT_Pay, then sum. For 2016 sum Gross_Wages, which is already combined.',
         'Subtract the 2015 total from the 2016 total. Joining raw rows would compare mismatched levels of detail.'], other=(current,))
    return exercises, contexts
