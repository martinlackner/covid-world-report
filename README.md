# covid-world-report
Creating maps showing the current state of the Covid pandemic

Based on data available from (https://ourworldindata.org/coronavirus).

Main feature: score-based evaluation of countries based on four variables (new_cases_smoothed_per_million,
positive_rate, new_deaths_smoothed_per_million, new_tests_smoothed_per_thousand).
Countries with insufficient information available are displayed grey.

## Scores

The score of a country is a positive number. A value of 0 indicates
that the situation is fully under control, a score between 0 and 100 corresponds to a situation that
is largely under control.
Scores of more than 100 indicate a significant spread of COVID-19.

The score is based on four variables (new_cases_smoothed_per_million, positive_rate, new_deaths_smoothed_per_million,
new_tests_smoothed_per_thousand) and calculated as follows:
There are three subscores:

```
score1 = new_cases_smoothed_per_million

score2 = max(0, 100 * (positive_rate - 0.04) / 0.04)

score3 = 100 * new_deaths_smoothed_per_million / 2
```

Then, the score of a country is the maximum of these three subscores.

In addition, the number of tests is taken into account.

If the score is < 200, then `new_tests_smoothed_per_thousand` has to be >= 0.1; otherwise the score is not displayed.
If `new_tests_smoothed_per_thousand` is not available for the current date, a value up to 30 days earlier is used.

If the score is < 50, then `new_tests_smoothed_per_thousand` has to be >= 0.5; otherwise the score is set to 50.
