---
title:  Random Samples from a Sphere
description: ''
pubDate: '26 Jul 2017'
heroImage: '/heroes/samples-from-a-sphere.png'
---

During my work today, at some point I had to draw samples uniformly from a sphere, and made an observation I hadn't really appreciated before. The name of the game is to make sure that every infinitesimal shell has the same density of samples, on average.

$$ \frac{4\pi r^2}{\left< N_{samp} \right>} = \mathrm{constant} $$

Or in other words, the volume gets more spread out, so we need more samples for higher r. The density is simply constant with respect to direction (angles). So, to get the correct distribution we simply need to sample from

$$ \theta \sim \mathcal{U}(0,2\pi) $$

$$ \phi \sim \mathcal{U}(0,\pi) $$

$$ r \sim r^2 $$

Or in other words, just sample from a power law distribution with index 2. Elementary observation? Maybe, but it makes it easier to code up!

<img src="/static/images/samplesFromASphere.png" alt="samples from a sphere" width="80%"/>
