import csv
import datetime
import sys
import folium
import geopandas as gpd
import wget
import os
import numpy as np
import branca.colormap as cmp
import shutil


def get_date_from_string(datestring):
    return datetime.datetime.strptime(datestring, "%Y-%m-%d").date()


def country_score_and_explanation(datarow):
    try:
        new_cases_smoothed_per_million = float(datarow["new_cases_smoothed_per_million"])
    except ValueError:
        new_cases_smoothed_per_million = None

    try:
        positive_rate = float(datarow["positive_rate"])
    except ValueError:
        positive_rate = None

    try:
        new_tests_smoothed_per_thousand = float(datarow["new_tests_smoothed_per_thousand"])
    except ValueError:
        new_tests_smoothed_per_thousand = None

    try:
        new_deaths_smoothed_per_million = float(datarow["new_deaths_smoothed_per_million"])
    except ValueError:
        new_deaths_smoothed_per_million = None

    subscores = []

    if new_cases_smoothed_per_million is None:
        subscores.append(None)
    else:
        subscores.append(100 * new_cases_smoothed_per_million / 100)
    if positive_rate is None:
        subscores.append(None)
    else:
        subscores.append(max(0., 100 * (positive_rate - 0.04) / 0.04))
    if new_deaths_smoothed_per_million is None:
        subscores.append(None)
    else:
        subscores.append(100 * new_deaths_smoothed_per_million / 2)

    missing = [x for x in subscores if x is None]
    explanationstr = "-------------------------------------<br>"

    if len(missing) == 3:
        maxscore = None
        explanationstr += f"too many missing datapoints<br>"
    else:
        maxscore = max(x for x in subscores if x is not None)

        if maxscore <= 200:
            if len(missing) > 1:
                maxscore = None
                explanationstr += f"too many missing datapoints for score < 200 ({len(missing)} of 3 missing)<br>"
            elif new_tests_smoothed_per_thousand is None:
                maxscore = None
                explanationstr += f"number of tests not reported in the last 30 days (and score <= 200)<br>"
            elif new_tests_smoothed_per_thousand < 0.1:
                maxscore = None
                explanationstr += f"too few tests for score < 200  (new_tests_smoothed_per_thousand < 0.1)<br>"

        if maxscore is not None and maxscore <= 50 and new_tests_smoothed_per_thousand < 0.5:
            maxscore = 50.01
            explanationstr += f"too few tests for score < 50 (requires new_tests_smoothed_per_thousand >= 0.5)<br>"

    def cond_print(x, prec=1):
        if x is None:
            return 'n/a'
        return f"{x:.{prec}f}"

    explanationstr += (f"score1 = {cond_print(subscores[0])} " +
                       f"(new_cases_smoothed_per_million = {cond_print(new_cases_smoothed_per_million)})<br>")
    explanationstr += f"score2 = {cond_print(subscores[1])} (positive_rate = {cond_print(positive_rate, 3)})<br>"
    explanationstr += (f"score3 = {cond_print(subscores[2])} " +
                       f"(new_deaths_smoothed_per_million = {cond_print(new_deaths_smoothed_per_million)})<br>")

    if maxscore is not None and maxscore > 200 and new_tests_smoothed_per_thousand is None:
        explanationstr += "number of tests not reported in the last 30 days (but score > 200)"

    if new_tests_smoothed_per_thousand is not None:
        explanationstr += (
            f"new_tests_smoothed_per_thousand = {new_tests_smoothed_per_thousand:.1f}" +
            f" (from {datarow['last_report_of_number_of_tests']})")

    return maxscore, explanationstr


def get_data_for_date(fulldata, date):
    data_for_date = {}
    for row in fulldata:
        country = row["location"]
        row_date = get_date_from_string(row["date"])
        if row_date == date:
            data_for_date[country] = row.copy()
            data_for_date[country]["last_report_of_number_of_tests"] = row["date"]

    # if number of tests is not (yet) reported for current date
    for row in fulldata:
        country = row["location"]
        if country not in data_for_date.keys():
            continue
        row_date = get_date_from_string(row["date"])
        if row_date > date or date - row_date > datetime.timedelta(days=30):
            continue
        if data_for_date[country]["new_tests_smoothed_per_thousand"] == "":
            data_for_date[country]["new_tests_smoothed_per_thousand"] = row["new_tests_smoothed_per_thousand"]
            data_for_date[country]["positive_rate"] = row["positive_rate"]
            data_for_date[country]["last_report_of_number_of_tests"] = row["date"]
        else:
            if (row_date > get_date_from_string(data_for_date[country]["last_report_of_number_of_tests"]) and
                    row["new_tests_smoothed_per_thousand"] != ""):
                data_for_date[country]["new_tests_smoothed_per_thousand"] = row["new_tests_smoothed_per_thousand"]
                data_for_date[country]["positive_rate"] = row["positive_rate"]
                data_for_date[country]["last_report_of_number_of_tests"] = row["date"]
    return data_for_date


def download():
    print('Downloading data ...')

    url = "https://covid.ourworldindata.org/data/owid-covid-data.csv"
    filename = "owid-covid-data.csv"
    if os.path.exists(filename):
        # os.rename(filename, filename+"("+str(datetime.datetime.now())+").csv")
        os.remove(filename)
    wget.download(url, filename)

    print('Download done.')


def generate_index_html(dates, date_extrainfo):
    # generate index.html
    html = """
    <!DOCTYPE html>
    <html>
    <body>
    """
    html += f"<h1 align=\"center\" style=\"font-size:16px\"><b>Covid scores</b></h1>"
    html += "<ul>"
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for date in sorted(dates, reverse=True):
        html += f"    <ul><a href=\"output/map-{date}.html\">{weekdays[date.weekday()]} {date}</a>: {date_extrainfo[date]}</ul>"
    html += """
    </ul>
    </body>
    </html>
    """
    with open("index.html", "w") as text_file:
        print(f"{html}", file=text_file)


def generate_folium_map(current_date, scores, geojson):


    print("generating map...")

    m = folium.Map(location=[45, 18], zoom_start=3, )

    colormap = cmp.LinearColormap(
        ['green', 'lightgreen'] + ['yellow'] * 2 + ['orange'] * 2 + ['darkorange'] * 2 + ['red'] * 4 + ['darkred'] * 8,
        caption='Covid score'
    ).to_step(index=[0, 25, 50, 100, 150, 200, 300, 500])

    folium.GeoJson(
        geojson,
        style_function=lambda feature: {
            'fillColor': (colormap(scores[feature["properties"]["NAME_LONG"]]) if
                          feature["properties"]["NAME_LONG"] in scores.keys() else "grey"),
            'color': 'black',
            'weight': 1.2,
            'fillOpacity': 0.6,
            'lineOpacity': 0.6,
        },
        tooltip=folium.features.GeoJsonTooltip(
            fields=["NAME_LONG_BOLD", "SCOREINFO", "DELTAINFO", "EXPLANATIONINFO"], labels=False)
    ).add_to(m)
    colormap.add_to(m)

    title_html = f"<h1 align=\"center\" style=\"font-size:16px\"><b>Covid score on {str(current_date)}</b></h1>"
    title_html += f"<h3 align=\"center\" style=\"font-size:14px\">{delta_msg}</h3>"
    m.get_root().html.add_child(folium.Element(title_html))

    m.save(f"output/map-{current_date}.html")
    print("---------------------------")

    info = (f"mean score: {np.mean(list(scores.values())):.1f} points, " +
            f"{len(scores)} scored countries")
    return info


def add_info_to_worldjson():
    scoreinfo = []
    explanationinfo = []
    boldnames = []
    deltainfo = []
    for country in worldjson["NAME_LONG"]:
        boldnames.append(f"<b>{country}</b>")
        if country in deltas.keys():
            deltainfo.append(f"delta from a week ago = {deltas[country]:+7.1f} points")
        else:
            deltainfo.append(f"delta from a week ago = n/a")
        if country in scores.keys():
            scoreinfo.append(f"score = <b>{scores[country]:.1f} points</b>")
            explanationinfo.append(explanations[country])
        elif country in unranked.keys():
            scoreinfo.append("score not available")
            explanationinfo.append(unranked[country])
        else:
            scoreinfo.append(f"no data available for {current_date}")
            explanationinfo.append("")
    worldjson["SCOREINFO"] = scoreinfo
    worldjson["DELTAINFO"] = deltainfo
    worldjson["EXPLANATIONINFO"] = explanationinfo
    worldjson["NAME_LONG_BOLD"] = boldnames


if __name__ == '__main__':
    if "--no-download" not in sys.argv[1:]:
        download()
    else:
        print("Option: --no-download used")

    # generate dates for which scores and maps are computed
    dates = set()
    if "--only-fridays" not in sys.argv[1:]:
        for daysago in [1, 2, 3]:
            dates.add(datetime.date.today() - datetime.timedelta(days=daysago))
    else:
        print("Option: --only-fridays used")
    current_date = datetime.date(2020, 3, 6)
    while current_date < datetime.date.today():
        dates.add(current_date)
        current_date += datetime.timedelta(days=7)
    #

    # clear output dir
    if os.path.exists("output"):
        # os.rename("output", "output-old-" + str(datetime.datetime.now()))
        shutil.rmtree("output")
    if not os.path.exists("output"):
        os.mkdir("output")
    #

    date_extrainfo = {}
    for current_date in dates:
        prevweek_date = current_date - datetime.timedelta(days=7)
    
        print(f"computing scores for {current_date}")
    
        data = []
        with open('owid-covid-data.csv') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                data.append(row)
    
        # make compatible with geojson
        for row in data:
            if row["location"] == "South Korea":
                row["location"] = "Republic of Korea"
            if row["location"] == "Russia":
                row["location"] = "Russian Federation"
            if row["location"] == "Democratic Republic of Congo":
                row["location"] = "Democratic Republic of the Congo"
            if row["location"] == "Sint Maarten (Dutch part)":
                row["location"] = "Sint Maarten"
            if row["location"] == "Cote d'Ivoire":
                row["location"] = "Côte d'Ivoire"
            if row["location"] == "Curacao":
                row["location"] = "Curaçao"
            if row["location"] == "North Macedonia":
                row["location"] = "Macedonia"
            if row["location"] == "Czechia":
                row["location"] = "Czech Republic"
            if row["location"] == "Cape Verde":
                row["location"] = "Republic of Cabo Verde"
        #
    
        current_data = get_data_for_date(data, current_date)
        prevweek_data = get_data_for_date(data, prevweek_date)
    
        scores = {}
        prev_scores = {}
        explanations = {}
        unranked = {}
    
        for country in current_data.keys():
            score, explanation = country_score_and_explanation(current_data[country])
            if score is None:
                unranked[country] = explanation
            else:
                scores[country] = score
                explanations[country] = explanation
    
        for country in prevweek_data.keys():
            score, _ = country_score_and_explanation(prevweek_data[country])
            if score is not None:
                prev_scores[country] = score
    
        # compute deltas
        deltas = {}
        for country in scores.keys():
            try:
                deltas[country] = scores[country] - prev_scores[country]
            except KeyError:
                pass
        #
    
        # print(f"{len(scores)} countries with sufficient information to be scored\n")
        # ranking = [(k, v) for k, v in sorted(scores.items(), key=lambda item: item[1], reverse=True)]
        # for i, (country, score) in enumerate(ranking):
        #     try:
        #         deltas[country] = score - prev_scores[country]
        #         deltastr = f"{deltas[country]:+7.1f}"
        #     except KeyError:
        #         pass
        #         deltastr = "n/a"
        #     print(f"{i+1:3d}. {country:35} ... {score:6.1f}  ({deltastr:>7s})  {explanations[country]:20s}")
    
        delta_msg = f"mean score: {np.mean(list(scores.values())):.1f} points ({len(scores)} countries), "
        delta_msg += f"delta from a week ago: {np.mean(list(deltas.values())):+.1f} points"
        print(delta_msg)

        worldjson = gpd.read_file("ne_10m_admin_0_countries.geojson")

        # warning if country with score is missing in geojson
        worldjson_countries = set(country for country in worldjson["NAME_LONG"])
        for country in scores.keys():
            if country not in worldjson_countries:
                print(f"Warning: country \"{country}\" not found in json file")

        add_info_to_worldjson()

        info = generate_folium_map(current_date, scores, worldjson)
        date_extrainfo[current_date] = info

    generate_index_html(dates, date_extrainfo)
    
    print("\nDone.")
