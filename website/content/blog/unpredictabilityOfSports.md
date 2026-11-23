---
title:  (un-)Predictability of Sports
description: ''
pubDate: '31 Dec 2017'
heroImage: '/heroes/unpredictability-of-sports.png'
---

A subject of debate (mostly in the pub) over the last few months has been about the predictability of sports results. My hypothesis was that the total number of points scored in a team-vs-team sport should be roughly Poisson distributed, and as such you would expect greater statistical fluctuations in the scores of sports where the score-lines are typically low (e.g. football), compared to sports with a high scoreline (e.g. Basketball). My thinking was that the "better" team should win more consistently in high scoreline sports.

Over the Christmas break, I decided to put my money where my mouth is, and actually investigate it. You can find the Jupyter notebook [here](/content/notebooks/rateOfUpsets.html). I downloaded a bunch of historical results from football, ice hockey and basketball, together with bookmakers pre-game odds. The data took a bit of cleaning, but I ultimately looked at how often the bookie's favourite lost for each sport. The tl;dr conclusion is that I was wrong. Football is the most accurately predicted, and has the lowest average scoreline.

<img src="/static/images/rateOfUpsets.png" alt="rate of upsets" width="80%"/>

I had intended to clean the notebook up a little bit, and make some more investigations (e.g. was I wrong because the score-lines aren't Poisson distributed? Or because each team's individual scoreline are too highly correlated with each other?) but whilst I was clearing out some of my external hard-drives I accidentally formatted my internal hard-drive too. That was a lot of fun to fix.... Anyway, I lost all my squeaky clean data, so I couldn't make prettier plots. Apologies.
