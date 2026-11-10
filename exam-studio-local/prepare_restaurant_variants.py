"""Fit additional four-question interpretation exams to the course workbook."""

import datetime as dt
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile

from prepare_regression import ROOT, SOURCE, fit, rows


def daily_data():
    with zipfile.ZipFile(SOURCE) as workbook:
        strings = [''.join(item.itertext()) for item in ET.fromstring(workbook.read('xl/sharedStrings.xml'))]
        sales, weather, games = (rows(workbook, sheet, strings) for sheet in (1, 3, 5))
    days = {}
    measures = ('netTotal', 'quantity', 'netTotal_7', 'netTotal_28', 'netTotal_364')
    for row in sales:
        day = days.setdefault(row['date'], dict.fromkeys(measures, 0.0))
        for measure in measures:
            day[measure] += row[measure]
    weather_by_date = {row['date']: row for row in weather}
    game_dates = {row['date'] for row in games if row['gameDay'] == 1}
    result = []
    for date, day in sorted(days.items()):
        if date not in weather_by_date:
            continue
        day.update(weather_by_date[date])
        for lag in (7, 28, 364):
            day[f'sales_{lag}_hundreds'] = day[f'netTotal_{lag}'] / 100
        day['game'] = int(date in game_dates)
        day['weekend'] = int((dt.date(1899, 12, 30) + dt.timedelta(days=date)).weekday() >= 5)
        day['wet'] = int(day['prcp'] > 0) if isinstance(day['prcp'], float) else None
        result.append(day)
    return result


def build_exam(number, data, outcome, predictor, indicator):
    outcome_field, outcome_label, outcome_unit = outcome
    x_field, x_label, x_unit = predictor
    z_field, z_label, z_description = indicator
    data = [dict(day, sales=day[outcome_field]) for day in data
            if day[x_field] is not None and day[z_field] is not None]
    x = lambda day: day[x_field]
    z = lambda day: day[z_field]
    lower, upper = min(map(x, data)), max(map(x, data))
    # Pick a typical observed reference-group value to avoid extrapolating.
    reference_values = sorted(x(day) for day in data if not z(day))
    point = reference_values[len(reference_values) // 2]
    point = round(point, 2)
    assert lower <= point <= upper
    prefix = f'REST-EXAM-{number:02}'
    definitions = [f'Outcome: {outcome_label} ({outcome_unit}).',
                   f'x = {x_label} ({x_unit}). Observed range: {lower:.2f} to {upper:.2f}.',
                   z_description]
    common = {
        'category': 'Data Interpretation', 'tool': 'Regression', 'case': 'Restaurant',
        'source_file': 'Restaurant/Instructions.docx and data.xlsm',
        'source_section': f'Adapted regression exam I{number:02}',
        'adaptation': 'Practice question written from a model fitted to the supplied Restaurant data. The question format is inspired by the course Exam Studio.',
        'model_notes': (
            'Daily sales, quantities and earlier sales are totals of the menu-item rows available on each date. '
            'Earlier sales use the history fields for items listed on the current date. Weather is joined by date. '
            'A game indicator uses listed games. Days with a missing predictor or grouping value are excluded. '
            'OLS p-values assume conventional independent, constant-variance errors. '
            'These fits describe associations and do not establish causal effects.'
        ),
    }
    items = []

    def add(suffix, title, skill, prompt, equation, model, answer, steps, binary=False):
        question = dict(common, id=f'{prefix}-{suffix}', title=title, skill=skill,
                        prompt=prompt, equation=equation, model=model,
                        definitions=definitions if binary else definitions[:2])
        items.append({'question': question, 'answer': answer, 'steps': steps})

    def coefficients(model):
        return [term['estimate'] for term in model['terms']]

    def p_summary(model, index):
        p = model['terms'][index]['p_value']
        return ('p < 0.0001' if p < .0001 else f'p ≈ {p:.4f}'), p < .05

    prediction = fit(data, [x_label, z_label], [x, z])
    a, b, c = coefficients(prediction)
    estimate = a + b * point
    add('P', f'Predict {outcome_label} from {x_label}', 'Prediction',
        f'Use the displayed model to predict {outcome_label} when {x_label} is {point:g} {x_unit} and {z_label} is 0. Show your substitution and round to two decimals.',
        'Predicted outcome = b₀ + b₁ × x + b₂ × z', prediction,
        f'{estimate:,.2f} {outcome_unit}',
        [f'Substitute x = {point:g} and z = 0: {a:.6f} + ({b:.6f} × {point:g}) + ({c:.6f} × 0).',
         'Round only the final predicted value.'], binary=True)

    simple = fit(data, [x_label], [x])
    slope = coefficients(simple)[1]
    p_text, significant = p_summary(simple, 1)
    add('S', f'Explain the {x_label} slope for {outcome_label}', 'Coefficient interpretation',
        f'Explain the coefficient on {x_label} in context, including its units and whether it is statistically significant at 5%.',
        'Predicted outcome = b₀ + b₁ × x', simple,
        f'A one-unit increase in {x_label}, measured in {x_unit}, is associated with {abs(slope):.6f} {outcome_unit} {"higher" if slope >= 0 else "lower"} predicted {outcome_label}. The coefficient is {"significant" if significant else "not significant"} at 5% ({p_text}).',
        ['Use the slope from this simple model. Interpret it as an association.'])

    quadratic = fit(data, [x_label, f'{x_label} squared'], [x, lambda day: x(day) ** 2])
    squared = coefficients(quadratic)[2]
    p_text, significant = p_summary(quadratic, 2)
    add('Q', f'Test curvature in the {x_label} relationship for {outcome_label}', 'P-values and nonlinearity',
        f'At 5%, does the squared {x_label} term support a curved relationship with {outcome_label}? Distinguish the shape of the fitted curve from the evidence for curvature.',
        'Predicted outcome = b₀ + b₁ × x + b₂ × x²', quadratic,
        f'The fitted curve is {"concave" if squared < 0 else "convex"}. The squared term {"supports curvature" if significant else "does not provide sufficient evidence for curvature"} at 5% ({p_text}).',
        ['Read the sign of the squared coefficient for the fitted shape.',
         'Compare its own p-value with 0.05. The marginal slope is b₁ + 2b₂ × x.'])

    interaction = fit(data, [x_label, z_label, f'{x_label} × {z_label}'], [x, z, lambda day: x(day) * z(day)])
    intercept, base_slope, shift, interaction_slope = coefficients(interaction)
    p_text, significant = p_summary(interaction, 3)
    add('I', f'Compare {x_label} slopes by {z_label} for {outcome_label}', 'Interaction interpretation',
        f'Interpret all four coefficients in context. How does the {x_label} slope change when {z_label} switches from 0 to 1? Is that difference statistically significant at 5%?',
        'Predicted outcome = b₀ + b₁ × x + b₂ × z + b₃ × x × z', interaction,
        f'The slopes are {base_slope:.6f} at z = 0 and {base_slope + interaction_slope:.6f} at z = 1, in {outcome_unit} per {x_unit}. The slope difference is {"significant" if significant else "not significant"} at 5% ({p_text}).',
        [f'The intercept {intercept:.6f} is the predicted outcome at x = 0 and z = 0. Compare x = 0 with the observed range.',
         f'The main effect of z, {shift:.6f}, is the difference between groups at x = 0.',
         f'The interaction {interaction_slope:.6f} is the change in slope between the groups.'], binary=True)
    return items


def main():
    data = daily_data()
    assert len(data) == 312
    sales = ('netTotal', 'daily sales', 'dollars')
    quantity = ('quantity', 'daily items sold', 'items')
    maximum = ('tmax', 'maximum temperature', '°F')
    minimum = ('tmin', 'minimum temperature', '°F')
    week = ('sales_7_hundreds', 'sales 7 days earlier', 'hundreds of dollars')
    month = ('sales_28_hundreds', 'sales 28 days earlier', 'hundreds of dollars')
    year = ('sales_364_hundreds', 'sales 364 days earlier', 'hundreds of dollars')
    game = ('game', 'game day', 'z = game day. 0 = no listed game, 1 = listed game.')
    weekend = ('weekend', 'weekend', 'z = weekend. 0 = weekday, 1 = Saturday or Sunday.')
    wet = ('wet', 'precipitation day', 'z = precipitation day. 0 = no precipitation, 1 = positive precipitation.')
    specs = [(sales, maximum, weekend), (sales, minimum, wet), (sales, week, game),
             (sales, month, weekend), (sales, year, wet), (quantity, maximum, game),
             (quantity, minimum, weekend), (quantity, week, wet), (quantity, month, game)]
    exercises = [item for number, spec in enumerate(specs, 2) for item in build_exam(number, data, *spec)]
    output = ROOT/'exam-studio-local/restaurant-variants.json'
    output.write_text(json.dumps({'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                                  'exercises': exercises}, ensure_ascii=False, indent=2)+'\n')
    print(f'{len(exercises)} questions from {len(specs)} sets of fitted models.')


if __name__ == '__main__':
    main()
