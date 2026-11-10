"""Build reproducible teaching output from the unmodified restaurant workbook."""
from pathlib import Path
import os
import csv
import hashlib
import json
import math
import xml.etree.ElementTree as ET
import zipfile
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(os.environ['EXAM_STUDIO_MATERIALS']) / '1. Excel part 4/Regression Assignment/Restaurant/data.xlsm'
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def beta_fraction(a, b, x):
    tiny=1e-300; c=1.; d=1-(a+b)*x/(a+1);d=1/(d if abs(d)>tiny else tiny);h=d
    for m in range(1,401):
        aa=m*(b-m)*x/((a+2*m-1)*(a+2*m))
        d=1+aa*d;d=d if abs(d)>tiny else tiny;c=1+aa/c;c=c if abs(c)>tiny else tiny;d=1/d;h*=d*c
        aa=-(a+m)*(a+b+m)*x/((a+2*m)*(a+2*m+1))
        d=1+aa*d;d=d if abs(d)>tiny else tiny;c=1+aa/c;c=c if abs(c)>tiny else tiny;d=1/d;delta=d*c;h*=delta
        if abs(delta-1)<3e-14:return h
    raise ArithmeticError('Incomplete beta did not converge')


def t_pvalue(t,df):
    x=df/(df+t*t);a=df/2;b=.5
    if x==1:return 1.
    front=math.exp(math.lgamma(a+b)-math.lgamma(a)-math.lgamma(b)+a*math.log(x)+b*math.log1p(-x))
    return front*beta_fraction(a,b,x)/a if x<(a+1)/(a+b+2) else 1-front*beta_fraction(b,a,1-x)/b


def rows(z,number,strings):
    result=[]
    for row in ET.fromstring(z.read(f'xl/worksheets/sheet{number}.xml')).findall('m:sheetData/m:row',NS):
        values={}
        for cell in row.findall('m:c',NS):
            value=cell.find('m:v',NS)
            if value is not None:values[''.join(filter(str.isalpha,cell.get('r')))]=strings[int(value.text)] if cell.get('t')=='s' else float(value.text)
        if values:result.append(values)
    header=result.pop(0)
    return [{name:row.get(col) for col,name in header.items()} for row in result]


def fit(data,names,columns):
    x=np.array([[1.]+[float(fn(row)) for fn in columns] for row in data]);y=np.array([row['sales'] for row in data])
    coef,_,rank,_=np.linalg.lstsq(x,y,rcond=None)
    assert rank==x.shape[1]
    residual=y-x@coef;df=len(y)-x.shape[1]
    covariance=np.linalg.inv(x.T@x)*float(residual@residual)/df
    se=np.sqrt(np.diag(covariance));p=[t_pvalue(float(t),df) for t in coef/se]
    assert np.max(np.abs(x.T@residual))<.1
    return {'n':len(data),'df':df,'terms':[{'name':name,'estimate':round(float(b),6),'p_value':float(pv)} for name,b,pv in zip(['Intercept']+names,coef,p)],'r_squared':1-float(residual@residual)/float((y-y.mean())@(y-y.mean()))}


def main():
    assert abs(t_pvalue(1,1)-.5)<1e-10
    assert abs(t_pvalue(2.2281388519649385,10)-.05)<1e-10
    assert t_pvalue(0,100)==1
    with zipfile.ZipFile(SOURCE) as z:
        strings=[''.join(n.itertext()) for n in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        sales=rows(z,1,strings);weather=rows(z,3,strings);games=rows(z,5,strings)
    day={}
    for row in sales:
        entry=day.setdefault(int(row['date']),{'sales':0.,'lag_sales':0.})
        entry['sales']+=row['netTotal'];entry['lag_sales']+=row['netTotal_364']
    weather_map={int(row['date']):row for row in weather};game_map={int(row['date']):row for row in games}
    assert len(weather_map)==len(weather) and len(game_map)==len(games)
    data=[]
    for date,row in sorted(day.items()):
        if date not in weather_map or weather_map[date]['tmax'] is None:continue
        data.append(dict(row,date=date,tmax=weather_map[date]['tmax'],game=game_map.get(date,{}).get('gameDay',0.)))
    models=[fit(data,['Maximum temperature (°F)','Game day'],[lambda r:r['tmax'],lambda r:r['game']]),fit(data,['Maximum temperature (°F)'],[lambda r:r['tmax']]),fit(data,['Maximum temperature (°F)','Maximum temperature squared (°F²)'],[lambda r:r['tmax'],lambda r:r['tmax']**2]),fit(data,['Sales 364 days earlier ($)','Game day','Earlier sales × Game day'],[lambda r:r['lag_sales'],lambda r:r['game'],lambda r:r['lag_sales']*r['game']])]
    base={'category':'Data Interpretation','tool':'Regression','case':'Restaurant','source_file':'Restaurant/Instructions.docx and data.xlsm','source_section':'Adapted regression-output exercises','adaptation':'New questions with OLS output calculated from the supplied Restaurant data, following the teacher’s interpretation question types. Not verbatim source questions or a teacher-issued exam.','model_notes':f'Daily sales are the sum of netTotal over the menu-item rows available for each date. Weather is joined on date; gameDay is 1 on a listed game date and assumed 0 on unlisted dates. Each model uses {len(data)} matched days. Maximum temperature is Fahrenheit; sales are before-tax dollars. Conventional OLS p-values are illustrative: daily residual independence/homoskedasticity is not established; associations do not prove causation. Use displayed coefficients for arithmetic.'}
    specs=[('P','Predict daily sales','Prediction','Using the supplied model, predict daily sales when maximum temperature is 60°F and there is no game (Game day = 0). Show your substitution and round dollars to two decimal places.','Predicted sales ($) = b₀ + b₁ × Temperature + b₂ × Game day'),('S','Interpret the temperature coefficient','Coefficient interpretation','Interpret the temperature coefficient in this model in context, including its units. Does its p-value provide evidence of an association at the 5% significance level? Avoid a causal claim.','Predicted sales ($) = b₀ + b₁ × Temperature'),('Q','Assess the squared temperature term','P-values and nonlinearity','What does the p-value of the squared temperature term tell you at the 5% significance level? Explain what you can and cannot conclude about the temperature–sales relationship.','Predicted sales ($) = b₀ + b₁ × Temperature + b₂ × Temperature²'),('I','Interpret the game-day interaction','Interaction interpretation','Interpret all four coefficients in context. Explain how the slope on sales 364 days earlier differs between game and non-game days; discuss the intercept cautiously.','Predicted sales ($) = b₀ + b₁ × Earlier sales + b₂ × Game day + b₃ × Earlier sales × Game day')]
    questions=[]
    for i,(suffix,title,skill,prompt,equation) in enumerate(specs):
        questions.append(dict(base,id='REST-REG-'+suffix,source_index=i+1,title=title,skill=skill,prompt=prompt,equation=equation,model=models[i],definitions=['Outcome: daily before-tax sales ($).','Game day: 0 = no listed football game; 1 = listed football game.','Earlier sales: sum of netTotal_364 for the menu items recorded on the current date, in dollars.'] if i==3 else ['Outcome: daily before-tax sales ($).','Temperature: daily maximum temperature (°F).','Game day: 0 = no listed football game; 1 = listed football game.']))
    for q in questions:
        if q['id'] in ('REST-REG-S','REST-REG-Q'):q['definitions']=[v for v in q['definitions'] if not v.startswith('Game day:')]
    assert min(r['tmax'] for r in data)<=60<=max(r['tmax'] for r in data)
    public=ROOT/'exam-studio-preview/questions.js';old=json.loads(public.read_text().split('=',1)[1].strip().rstrip(';'));old=[q for q in old if not q['id'].startswith('REST-REG-') and q['id'] not in ('CS50-SONGS-002','CS50-SONGS-003')]
    for index,title,prompt,skill in [(2,'Order songs by tempo','In 2.sql, write a SQL query to list the names of all songs in decreasing order of tempo.','Sorting'),(3,'Find the three longest songs','In 3.sql, write a SQL query to list the names of the top 3 longest songs, in descending order of length.','Sorting and limits')]:
        old.append({'id':f'CS50-SONGS-{index:03}','source_index':index,'tool':'SQL','category':'Data Manipulation','case':'CS50 Songs','source_file':'songs/requierements.txt','source_section':f'Before relational · {index}.sql','title':title,'prompt':prompt,'skill':skill,'output_requirement':'Output one column containing the song names.','dataset':'songs.db'})
    public.write_text('window.EXAM_QUESTIONS = '+json.dumps(old+questions,ensure_ascii=False,indent=2)+';\n')
    output=ROOT/'exam-studio-discovery'
    with (output/'restaurant-daily-model-input.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['date','sales','lag_sales','tmax','game']);writer.writeheader();writer.writerows(data)
    audit={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'source_sales_rows':len(sales),'matched_daily_rows':len(data),'game_dates_matched':sum(r['game']==1 for r in data),'source_total_sales':sum(r['netTotal'] for r in sales),'aggregated_total_sales':sum(r['sales'] for r in day.values()),'models':models,'prediction_using_displayed_coefficients':round(models[0]['terms'][0]['estimate']+60*models[0]['terms'][1]['estimate'],2),'controls':['OLS normal-equation residual orthogonality checked','p-value implementation checked against exact df=1 and known df=10 values','No missing model predictor silently replaced, except documented non-game-day assumption'],'limits':base['model_notes']}
    assert math.isclose(audit['source_total_sales'],audit['aggregated_total_sales'],abs_tol=1e-6)
    (output/'restaurant-model-audit.json').write_text(json.dumps(audit,indent=2))
    print(json.dumps({'days':len(data),'game_dates':audit['game_dates_matched'],'models':models,'prediction':audit['prediction_using_displayed_coefficients']},indent=2))


if __name__=='__main__':main()
