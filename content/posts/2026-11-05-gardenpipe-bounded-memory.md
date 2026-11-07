---
title: "Arbitrarily large data, bounded memory"
subtitle: "What does a training run actually need to remember?"
slug: gardenpipe-bounded-memory
date: 2026-11-05
summary: "We introduce GardenPipe, a training framework for a single workstation that treats memory as a budget you set. Its guarantee rests on one question: how little of the past can each step keep?"
tags: [Machine learning, Systems]
draft: true
---

<!-- i18n: gardenpipe.block001 -->

Most people who train models on limited hardware know this failure. You start a promising run, go to bed, and find in the morning that the process was killed 22 minutes after it started. The error names memory, but not the decision that spent it.

<!-- i18n: gardenpipe.block002 -->

That is what makes out-of-memory errors expensive. Peak memory is usually a side effect of the file reader, the feature code, the prefetch queue, and the model, each reasonable on its own. Nobody wrote the number down, so nothing could check it before the run began. The usual remedies work around the problem: a larger machine, a sample of the data, or a cluster for a job that one workstation could do.

<!-- i18n: gardenpipe.block003 -->

GardenPipe starts from a different premise: memory is an input you set, not an output you discover. The name comes from the difference between a fire main and a garden hose. With a fire main there is capacity to spare, and a surge simply goes somewhere. With a garden hose you are watering beds you care about, so you want a steady stream whose rate you control. Data work on one machine is the garden case. The dataset on disk can be many times larger than RAM, and one careless `collect()` floods the machine.

<!-- i18n: gardenpipe.block004 -->

In this note, we describe the memory model rather than the code. We begin with the budget and the question underneath it: what does a training run actually need to remember? We then measure whether the bound holds, up to a billion rows on a machine with 31 GiB of RAM. That measurement found a term we had left out of the budget, and the fix came from the same question. Finally, we use real weather data to check that streaming does not change the answer, and to assess how good the fit is. That assessment is less flattering than the first table suggests, and it leads back to memory.

<!-- i18n: gardenpipe.block005 -->

**In this note:** [The budget](#budget) · [What to remember](#state) · [Does it hold?](#bound) · [The missing term](#density) · [Weather](#weather) · [The fit](#fit) · [Width, not length](#width) · [Limits](#limits)

<!-- i18n: gardenpipe.block006 -->

## Memory as a budget {#budget}

<!-- i18n: gardenpipe.block007 -->

The guarantee is easy to state: growing the dataset adds time, not memory, whether it grows by more dates or by more rows in each date. GardenPipe reads one date at a time, cuts each date into windows of about `batch_size` rows, and hands the model fixed-size batches. Peak memory is then roughly a sum of six terms. The table gives the shape of that sum, not its size: reader and allocator buffers turn out to be the largest term, and we measure them below.

<!-- i18n: gardenpipe.block008 -->

| Term | Set by | Grows with the data? |
| --- | --- | --- |
| Interpreter and libraries | Your environment | No |
| Reader and allocator buffers | Thread count | No |
| One window and its look-ahead | Batch size, target horizon | Only if the horizon spans more rows |
| One batch: rows × columns × 8 bytes | Batch size, feature count | No |
| Prefetch | A budget in bytes | No |
| Model state | The model | Depends on the model |

<!-- i18n: gardenpipe.block009 -->

<figure class="note-figure">
  <div class="diagram-scroll" tabindex="0" role="region" aria-label="What grows with the data"><img src="/assets/posts/gardenpipe-bounded-memory/budget.svg" width="720" height="332" alt="Files on disk, one per date, grow with the data. In memory, one window, one batch, a prefetch budget, the interpreter and reader buffers, and model state are fixed by settings chosen before the run." loading="lazy"></div>
  <figcaption>Only the files on the left grow with the data. Everything on the right is set before the run begins, apart from model state, which depends on the model.</figcaption>
</figure>

<!-- i18n: gardenpipe.block010 -->

Two design choices make this more than arithmetic. First, prefetch is budgeted in bytes, not queue slots. A queue of ten batches is not a memory bound, because it says nothing about how large a batch is. Each worker reserves credit before it builds a batch, the credit travels with the batch, and it is released only when the consumer lets go. While a batch exists both as a DataFrame and as NumPy arrays, it is charged twice.

<!-- i18n: gardenpipe.block011 -->

Second, a budget that cannot work fails at the start. If prefetch cannot hold what a pass needs, GardenPipe rejects it before any worker starts. In our test, a 1 MiB budget stopped after 0.3 seconds, with an error stating what it needed: 12 million bytes, or a batch of at most 8,738 rows. That is the same mistake as the failure at minute 22, at a much lower price.

<!-- i18n: gardenpipe.block012 -->

## What has to be remembered {#state}

<!-- i18n: gardenpipe.block013 -->

Streaming is easy. Streaming without changing the answer is the hard part. Cut a dataset into batches naively, and every exponential average restarts at the boundary, every lag goes missing, and every target near the edge disappears. The output looks plausible and is wrong.

<!-- i18n: gardenpipe.block014 -->

The useful question is therefore not how large the data are, but how much of the past each step must keep. A physicist would recognize the idea: a state is the smallest description of the past that makes the future independent of it. GardenPipe looks for such a state for everything that crosses a batch boundary.

<!-- i18n: gardenpipe.block015 -->

| What crosses a boundary | What it must keep | Grows with rows? |
| --- | --- | --- |
| Where the next window starts | One row number | No |
| Exponential average | One value and one timestamp | No |
| Lag or rolling window | That much history | No |
| Forward target | One horizon of look-ahead | Only if the horizon spans more rows |
| Ridge regression | *X′X*, *X′y*, and the means | No |
| Neural network | Weights and optimizer state | No |
| Boosted trees, in core | A quantized copy of the rows | Yes |

<!-- i18n: gardenpipe.block016 -->

The ridge row deserves attention. For a linear model, *X′X* and *X′y* are sufficient statistics: they hold everything the data can tell the model. A billion rows with 20 features compress, without loss, to a 20 × 20 matrix. The result is not an approximation to the full-data solution. It is that solution.

<!-- i18n: gardenpipe.block017 -->

The price is discipline. Files must be sorted by time. Plain feature expressions must be local to a row or a timestamp. Anything that needs history has to be declared as state. We think this is the right trade, because it turns a hidden dependency on the past into a declared one with a known size.

<!-- i18n: gardenpipe.block018 -->

## Does the bound hold? {#bound}

<!-- i18n: gardenpipe.block019 -->

We measured this on generated data: one mean-reverting series at four million rows per day, an exponential average, a five-minute forward target, and ridge regression over walk-forward folds. Each run was a fresh process on a 12-core, 20-thread machine with 31 GiB of RAM, and each began with its files out of the page cache, because data larger than RAM cannot all sit there. The control is the same pipeline with one flag changed, so that each source is materialized in memory instead of streamed. These runs include two fixes that the measurements themselves forced, which we describe [below](#density).

<!-- i18n: gardenpipe.block020 -->

| Rows | On disk | Streamed peak | Materialized peak | Streamed time | Materialized time |
| --- | ---: | ---: | ---: | ---: | ---: |
| 20 million | 205 MiB | 590 MiB | 1.5 GiB | 25 s | 18 s |
| 40 million | 409 MiB | 609 MiB | 2.4 GiB | 47 s | 37 s |
| 80 million | 818 MiB | 604 MiB | 4.1 GiB | 97 s | 74 s |
| 120 million | 1.2 GiB | 622 MiB | 6.0 GiB | 148 s | 107 s |
| 240 million | 2.4 GiB | 623 MiB | 11.7 GiB | 299 s | 217 s |
| 360 million | 3.6 GiB | 619 MiB | 16.5 GiB | 440 s | 331 s |

<!-- i18n: gardenpipe.block021 -->

While the data grow eighteenfold, the streamed peak moves from 590 to 619 MiB. Five runs of the 30-date job peaked between 586 and 622 MiB, and the 60- and 90-date runs reached 623 and 619 MiB, so that movement is no larger than the spread between repeats of one job. The materialized peak climbs by about 4.5 GiB per 100 million rows. The two modes agree on test R² to within 2 × 10<sup>−15</sup> at every size. Streaming pays in time, taking 1.3 to 1.4 times as long, because each window is read and computed separately.

<!-- i18n: gardenpipe.block022 -->

<figure class="note-figure">
  <div class="diagram-scroll" tabindex="0" role="region" aria-label="Peak memory against dataset size"><img src="/assets/posts/gardenpipe-bounded-memory/scale.svg" width="720" height="356" alt="Peak memory of the materialized run rises in a straight line with the number of rows. Peak memory of the streamed run stays flat." loading="lazy"></div>
  <figcaption>Same pipeline, same data, same test score. One flag changes how the data reach the model.</figcaption>
</figure>

<!-- i18n: gardenpipe.block023 -->

A peak is an observation, not a bound, so we also enforced one. We ran both modes on 30 days of data, 120 million rows, under a 1 GiB cgroup limit with swap disabled. The streamed run finished in 148 seconds, peaking at 586 MiB. The materialized run looked healthier for most of its life: for 21 seconds it never passed 550 MiB, while the streamed run touched 563 MiB over the same stretch. Then it went from 550 MiB to the limit in under half a second, and the kernel killed it a second later. Nothing in those 21 seconds would have warned anyone.

<!-- i18n: gardenpipe.block024 -->

<figure class="note-figure">
  <div class="diagram-scroll" tabindex="0" role="region" aria-label="Memory over time under a limit"><img src="/assets/posts/gardenpipe-bounded-memory/cap.svg" width="720" height="320" alt="Under a one gibibyte limit, the streamed run stays below the limit until it finishes. The materialized run climbs to the limit and is killed." loading="lazy"></div>
  <figcaption>RSS of each Python process, sampled five times a second. RSS also counts mapped files that the limit may not charge to the process, so it can sit slightly above the line.</figcaption>
</figure>

<!-- i18n: gardenpipe.block025 -->

The same limit held for a billion rows, at ten million rows per date over 100 dates, 9.8 GiB of compressed Parquet. Two runs each finished in under 22 minutes, peaking at 701 and 695 MiB. That is about 90 MiB above ten dates at the same density. The extra height sits in the same two stretches of both runs and then drains away, so it is not accumulation, but we have not traced it. The test fold alone is 199 million rows. Extrapolating the materialized line puts the same job at about 45 GiB, more memory than the machine has.

<!-- i18n: gardenpipe.block026 -->

Within the bound, the peak still depends on what you choose. Batch size moves it most, and it trades memory against time. Each row below is the same 40-million-row job, with the prefetch budget raised to fit the largest batches, and test R² agrees across all of them to within 10<sup>−15</sup>.

<!-- i18n: gardenpipe.block027 -->

| Batch, rows | Peak | Time |
| ---: | ---: | ---: |
| 25,000 | 453 MiB | 120 s |
| 50,000 | 509 MiB | 79 s |
| 100,000 | 592 MiB | 47 s |
| 200,000 | 671 MiB | 35 s |
| 400,000 | 863 MiB | 28 s |
| 800,000 | 1.1 GiB | 25 s |
| 1,600,000 | 1.6 GiB | 24 s |

<!-- i18n: gardenpipe.block028 -->

Workers add memory too: 557 MiB with one, 615 with two, 718 with four, and 825 with eight. The prefetch budget barely matters in these runs, with peaks of 557 to 620 MiB from a 16 MiB budget to a 1 GiB one, because ridge empties the queue as fast as the workers fill it. With a slow consumer it binds, as it should: holding each batch for 300 ms, the peak goes from 554 MiB at a 16 MiB budget to 1.9 GiB at a 1 GiB budget.

The largest constant is one we did not plan for. Polars sizes its buffers from the thread count, and the allocator decides how quickly freed memory goes back. At the default of 20 threads, a five-date run peaks at 585 MiB. At two threads it peaks at 375 MiB and finishes in 16 seconds instead of 24. With four threads and the allocator told to return memory at once, it peaks at 273 MiB. We did not trace why fewer threads run faster here, and this is one job on one machine, but `POLARS_MAX_THREADS` is worth trying before buying memory.

<!-- i18n: gardenpipe.density001 -->

## The term we left out {#density}

<!-- i18n: gardenpipe.density002 -->

Every run so far grows the dataset the same way: more dates. That is the easy direction, because a date is the unit GardenPipe reads one at a time. So we also grew it the other way, keeping five dates and raising the rows per date from 1 million to 80 million, with the same five-minute horizon.

<!-- i18n: gardenpipe.density003 -->

On the first version of the code, this test failed. The peak doubled from 554 MiB to 1.1 GiB, past the limit that every run above had cleared, and the time per row more than tripled. The results above already include the two fixes that came out of it, but that first version had been just as flat along the dates axis, at 670 to 730 MiB. A flat line along one axis had told us nothing about the other.

<!-- i18n: gardenpipe.density004 -->

The obvious suspects were innocent. Replacing ridge with a loop that discards each batch moved the peak by at most 43 MiB. The allocator, told to return freed memory at once, lowered the peak by about 250 MiB at both sizes we tried, so it set the level but not the slope. Look-ahead seemed certain, because a five-minute horizon holds 20 times as many rows at 80 million rows per date as at 4 million. But when we shortened the horizon to hold the look-ahead at 13,888 rows, the peak still rose, from 672 MiB to 1,064 MiB.

<!-- i18n: gardenpipe.density005 -->

**Time came from a filter.** Each window is read with an upper bound on time. Parquet files record the range of times in each row group, so a reader can skip everything beyond the window without touching it. But we had written the bound on a computed expression, the time converted to an integer, and a reader cannot compare an expression with its statistics. So every window read on to the end of the date: at the start of an 80-million-row file, 650 of 651 row groups, where a handful would do. Writing the same bound on the column itself took that job from 25 minutes to 11.

<!-- i18n: gardenpipe.density006 -->

**Memory came from a query.** To cut a date into windows, GardenPipe needs the next chunk of timestamps, and it took them from one query held open across the whole date. That looks harmless, since it consumes only a few chunks at a time. But an open query is not a cursor. A streaming engine works ahead of a slow consumer. At 20 threads, this one held up to about 200 MiB of what look like decoded timestamps, plus compressed read-ahead that grew with the file. Training holds two dates open, so that cost counted twice. It appeared on no line of our budget, and lowering the engine's read-ahead setting removed only part of it.

<!-- i18n: gardenpipe.density007 -->

The fix came from the question of this note. What does cutting a date into windows actually need to remember between windows? One integer: the row it has reached. So each chunk of timestamps is now its own short query, which starts at that row and reads a row group or two. The open query had been storing hundreds of megabytes in place of one number. The short queries are not free: they add 3 to 5 seconds to a 40-million-row job, and fetching more timestamps per query wins that back by spending about 100 MiB of the peak. We kept the memory.

<!-- i18n: gardenpipe.density008 -->

<figure class="note-figure">
  <div class="diagram-scroll" tabindex="0" role="region" aria-label="Peak memory against rows per date"><img src="/assets/posts/gardenpipe-bounded-memory/density.svg" width="720" height="356" alt="Peak memory against rows per date. The first version climbs past the 1 GiB limit. With both fixes the peak stays between 500 and 720 MiB, and it is flat when the look-ahead is held fixed." loading="lazy"></div>
  <figcaption>Five dates at each density. The dashed line shortens the horizon so that the look-ahead stays at 13,888 rows.</figcaption>
</figure>

<!-- i18n: gardenpipe.density009 -->

With both changes and the look-ahead held at 13,888 rows, the peak stays between 584 and 617 MiB from 4 million to 80 million rows per date, and time stays between 1.23 and 1.29 seconds per million rows. With the five-minute horizon it rises to 722 MiB, about 540 bytes for each row of look-ahead. That remaining rise is the third line of the budget: a term we declared, at a size we can predict. A single peak is only good to a few tens of MiB, though: repeats of one job at 8 million rows per date ranged from 603 to 692 MiB. Neither change moved the answer. No fitted coefficient changed by more than 5 × 10<sup>−16</sup>, and the weather forecasts below are identical to the last bit.

<!-- i18n: gardenpipe.density010 -->

Under the 1 GiB limit, this is the difference between a result and a failure. On the 80-million-row job, the first version was killed after 220 seconds, and the fixed one finished in 11 minutes, peaking at 690 MiB.

<!-- i18n: gardenpipe.density011 -->

This is the failure from the opening of this note, in our own code. Peak memory was a side effect of a reasonable decision, and nobody had written the number down. A term that is not written down is not bounded, however flat the line you happened to draw.

<!-- i18n: gardenpipe.block029 -->

## A real dataset: six-hour temperature forecasts {#weather}

<!-- i18n: gardenpipe.block030 -->

Generated data can demonstrate a bound, but not that a method is correct on real observations. For that, we use the Jena weather archive: eight years of fourteen measurements every ten minutes from one station, 420,223 rows in all. Memory is not the point here, because the data fit comfortably in RAM. That is exactly what makes them useful: we can compare streaming with a full pass.

<!-- i18n: gardenpipe.block031 -->

The task is to forecast the temperature change over the next six hours, from every full hour. The 18 features include wind components, calendar terms, differences against earlier observations, and exponential averages of temperature and pressure. A label requires an observation at exactly six hours ahead; across a gap it is missing rather than borrowed from a nearby reading. Folds follow the calendar. Regularization is chosen on 2013 and 2014, the model is refitted on 2009–2014, and 2015–2016 are tested once.

<!-- i18n: gardenpipe.block032 -->

We start with the test that matters most for this note. We fitted ridge with batches of 5,000 rows, with batches of 20,000 rows, and with one batch per year. Across all 17,377 test forecasts, the three runs agree to better than **10<sup>−11</sup> °C**. We then rewrote the whole pipeline without GardenPipe, as one in-memory pass: features, labels, folds, scaling, and solve. It selects the same 17,377 issue times, and its forecasts match the streamed ones to better than **10<sup>−5</sup> °C**. Streaming did not change the answer.

<!-- i18n: gardenpipe.block033 -->

| Forecast | MAE, °C | RMSE, °C | MAE skill |
| --- | ---: | ---: | ---: |
| Persistence | 3.26 | 4.29 | – |
| Daily persistence | 2.62 | 3.42 | 19.6% |
| Ridge, calendar features | 1.97 | 2.56 | 39.6% |
| Ridge, all 18 features | 1.70 | 2.21 | 47.7% |

<!-- i18n: gardenpipe.block034 -->

Persistence assumes the temperature will not change. Daily persistence uses the temperature at the target hour one day earlier. Skill is the reduction in absolute error relative to persistence. On these numbers, ridge cuts the error of the naive forecast nearly in half.

<!-- i18n: gardenpipe.block035 -->

<figure class="note-figure">
  <div class="diagram-scroll" tabindex="0" role="region" aria-label="Forecasts for two weeks"><img src="/assets/posts/gardenpipe-bounded-memory/weeks.svg" width="720" height="444" alt="Observed temperature with ridge and persistence forecasts for one winter week and one summer week of 2015. Ridge follows the daily cycle; persistence lags it by six hours." loading="lazy"></div>
  <figcaption>The two weeks were fixed in advance. Each point is a forecast issued six hours earlier.</figcaption>
</figure>

<!-- i18n: gardenpipe.block036 -->

## How good is the fit? {#fit}

<!-- i18n: gardenpipe.block037 -->

Start with the flattering number. R² on temperature itself is **0.92**, but that says little, because persistence already reaches 0.71. The honest target is the six-hour change, where R² is **0.74**.

<!-- i18n: gardenpipe.block038 -->

By the standard checks, the model behaves well. RMSE is 2.20 °C on the training years and 2.21 °C on the test years, and both test years sit inside the 2.05–2.37 °C spread of the training years. Regularization hardly matters: validation RMSE moves by less than 0.01 °C between α = 0.1 and α = 1,000. Regressing the observed change on the forecast gives a slope of 1.00. A weekly block bootstrap gives 95% intervals of 1.64–1.77 °C for test MAE and 44–51% for skill.

<!-- i18n: gardenpipe.block039 -->

Errors also behave as a good forecast's should. Neighboring six-hour forecasts share most of their window, so errors correlate at 0.86 after one hour and 0.49 after three. At six hours, once the windows no longer overlap, the correlation falls to **0.01**. Past errors no longer say anything about future ones.

<!-- i18n: gardenpipe.block040 -->

The largest errors come from weather that one station cannot see coming. The worst forecast in the two test years was issued at 07:00 on 1 June 2015. The model expected 22.2 °C at 13:00, and the station recorded 10.3 °C. Humidity was 68% when the forecast was issued and 81% an hour later, and the temperature fell through a morning that normally warms. The worst 1% of hours hold 12% of the squared error.

<!-- i18n: gardenpipe.block041 -->

So far, this reads like a good model. It is not quite one. In the 5% of hours where it forecasts the strongest warming, the model expects 7.3 °C and the station records 8.7 °C. Mean error by month and issue hour shows more: forecasts issued on August mornings run up to 2.1 °C too cold, and those issued on December afternoons up to 1.4 °C too warm. With 288 cells this could be noise, but it is not. The pattern correlates at **0.81** between 2015 and 2016.

<!-- i18n: gardenpipe.block043 -->

The direct test is to fit a more flexible model on the same inputs, folds, and test rows. Gradient boosting, selected on the validation folds, reaches an MAE of **1.33 °C**. That is 22% lower than ridge (95% interval 20.1–23.4%), and it is lower in every month and at every issue hour. Adding season-by-hour terms to ridge helps only a little, to 1.64 °C, so the missing structure is not one interaction.

<!-- i18n: gardenpipe.block042 -->

<figure class="note-figure">
  <div class="diagram-scroll" tabindex="0" role="region" aria-label="Mean forecast error by month and hour"><img src="/assets/posts/gardenpipe-bounded-memory/bias-map.svg" width="720" height="396" alt="Two heat maps of mean forecast error by month and issue hour. The ridge model shows bands of bias of up to two degrees. Gradient boosting shows far less structure." loading="lazy"></div>
  <figcaption>Each cell averages about 60 forecasts from 2015–2016. The left pattern repeats between the two years, with a correlation of 0.81. The right pattern barely does, at 0.11.</figcaption>
</figure>

<!-- i18n: gardenpipe.block044 -->

This is the main lesson of the exercise. Every check above passed, and the model still left more than a fifth of its error on the table. A small train–test gap and a slope of one show that a model is not overfitting. Uncorrelated errors show that past errors cannot predict future ones. None of them shows that the inputs have been used well. Ridge is an honest model here, but an underfitted one.

<!-- i18n: gardenpipe.block045 -->

## Spend memory on width, not length {#width}

<!-- i18n: gardenpipe.block046 -->

There is an uncomfortable detail in that result. The most accurate model so far is also the one with the weakest memory guarantee. In-core gradient boosting holds a quantized copy of the rows, about 46 bytes per row on the generated data. XGBoost's external-memory mode saved 17–21% of the peak at 1.4 to 1.5 times the time, and it still grew by 39 bytes per row. Under a 2 GiB limit on 40 million rows, the in-core run was killed and the external one finished at 1.8 GiB. Under 1 GiB, both were killed.

<!-- i18n: gardenpipe.block047 -->

Ridge offers another route, because its state grows with the number of features, not the number of rows. That suggests spending memory on width instead of length. We project the 18 standardized inputs onto random directions and take cosines. These are [random Fourier features](https://papers.nips.cc/paper/3182-random-features-for-large-scale-kernel-machines), and a linear model on them approximates a kernel machine. However many rows pass through, *X′X* stays the same size.

<!-- i18n: gardenpipe.block048 -->

| Model | Test MAE, °C | Test RMSE, °C | Peak RSS, MiB | Time, s |
| --- | ---: | ---: | ---: | ---: |
| Ridge, 18 features | 1.70 | 2.21 | 250 | 9 |
| Ridge, 500 random features | 1.42 | 1.87 | 304 | 14 |
| Ridge, 2,000 random features | 1.36 | 1.79 | 461 | 26 |
| Ridge, 4,000 random features | 1.35 | 1.78 | 1,063 | 62 |
| Gradient boosting | 1.33 | 1.77 | 493 | 19 |

<!-- i18n: gardenpipe.block049 -->

With 2,000 features, streamed through the same pipeline, ridge comes within about 2% of gradient boosting, and with 4,000 within about 1%. Four random seeds give MAEs from 1.35 to 1.37 °C at 2,000 features. The month-by-hour pattern almost disappears, with its correlation between years falling to 0.11, and the *X′X* matrix takes 31 MiB, whether a thousand rows pass through or a billion.

<!-- i18n: gardenpipe.block050 -->

<figure class="note-figure">
  <div class="diagram-scroll" tabindex="0" role="region" aria-label="Test error against model width"><img src="/assets/posts/gardenpipe-bounded-memory/width.svg" width="720" height="340" alt="Test error falls as the linear model widens and approaches the gradient boosting level. Labels give the size of the X prime X matrix." loading="lazy"></div>
  <figcaption>Labels give the size of the <em>X′X</em> matrix, which does not depend on the number of rows.</figcaption>
</figure>

<!-- i18n: gardenpipe.block051 -->

We do not claim that random features generally keep up with boosting. This is one small dataset, and we compared only two kernel widths, on the validation folds. The cost also moves, as it should: with 2,000 features, fitting took three times as long, the peak rose by about 210 MiB, and each row updates a matrix of about four million entries. All of that grows with the width, which we chose before the run. None of it grows with the rows. Averaging the two models gives an MAE of 1.32 °C, so neither has exhausted these inputs.

<!-- i18n: gardenpipe.block052 -->

## What the bound does not cover {#limits}

<!-- i18n: gardenpipe.block053 -->

"Arbitrarily large" has a precise meaning here. The bound concerns the number of dates and the rows in each date, with a few exceptions worth stating.

<!-- i18n: gardenpipe.block054 -->

- **Look-ahead is counted in rows.** A horizon in minutes holds more rows as the data get denser, at about 540 bytes per row here. With one source, it is the one term that still grows with rows per date.
- **One timestamp is indivisible.** A window never splits a timestamp, so a burst of rows at one time makes a larger batch.
- **A date without windows is a unit of its own.** With no target or front pad, the streaming scan can hold most of a date, so very large dates should be split into smaller files.
- **The budget counts batches.** Reader and allocator buffers sit outside it. With a slow consumer, each MiB of budget added about 1.4 MiB to the peak, so leave a margin.
- **Convenience spends the budget.** Keeping every prediction, caching arrays across trials, or using a non-streaming adapter all trade the bound for speed or ease.
- **Small batches cost time.** Each window is a separate read. On the weather data, 5,000-row batches took 40 seconds, and one batch per year took 10.
- **Joining streams still rises, slowly.** These runs stream one source at a time. Joining several streams goes through other code, which needed the same two changes, now in [commit `693cc4b`](https://github.com/LiJ21/GardenPipe/commit/693cc4b52b3d89e16585af2b3cd6a894f878c87c). With three streams in one shared file, they took 40M rows per date from 1,423 MiB to about 600 MiB, in less than half the time. The peak still reaches 739 MiB at 80M: each date opens with a pass over its whole file, and that part still grows with rows per date.
- **One machine is still one machine.** Time grows with the data, so a job with a deadline may need more hardware regardless of memory.

<!-- i18n: gardenpipe.block055 -->

None of this makes a cluster unnecessary. It does change the first question. Before asking how much memory a job needs, ask what each step must remember. For features and linear statistics, the answer is very little, and it is known before the run starts. For everything else, the answer is at least a number you chose rather than one you discover at minute 22.

<!-- i18n: gardenpipe.block056 -->

The [GardenPipe repository](https://github.com/LiJ21/GardenPipe) contains the framework and the [weather example](https://github.com/LiJ21/GardenPipe/tree/9bc5e3e7c98cd04fa104a4ef629a20137290eff6/examples/weather). The [scripts behind these measurements](https://github.com/LiJ21/LiJ21.github.io/tree/main/scripts/gardenpipe_note) record the configurations. They ran against commit `9bc5e3e` with the two changes described above, which are now in [commit `89d7244`](https://github.com/LiJ21/GardenPipe/commit/89d72445201635a99b3ee373ba4782bababf7cf0), together with a small guard for unusual time columns that leaves these results as they are. That folder keeps the changes as patch files, alongside the results for the commit as published.
