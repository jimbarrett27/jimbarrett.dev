---
title:  Gaussian Process Update Equations
description: ''
pubDate: '14 Jul 2017'
heroImage: '/heroes/gaussian-process-update-equations.png'
---

When you start to learn about Gaussian processes, you come across the update equations fairly early on. The update equations are fairly intimidating to look at, and are typically dismissed as trivial to derive (for example, Rasmussen and Williams simply point you towards a statistics book from the 1930's, which is neither available online nor in our university library...). I had a go at the derivation, and promptly realised it wasn't trivial at all from a cold start.

Fortuitously, at the PEN emulators workshop I recently attended, there was an introductory lecture from Jochen Voss, where he went through a univariate case, and then gave us the structure of the derivation for the full multivariate case. Luckily, this gave me the push I needed to try the derivation again, so I went away and filled in the gaps.

So here it is, in all it's glory; the derivation of the update equations for Gaussian processes.

The overall endgame of Gaussian process regression is to write down a conditional distribution $ P(y_p | y_t) $ for a set of predicted outputs $y_p$ given a set of training (observed) outputs $y_t$. By the product rule

$$ P(y_p|y_t) = \frac{P(y_p,y_t)}{P(y_t)} $$

Since we have a constant set of data, $P(y_t)$ is just a constant in this expression.

The underlying assumption in Gaussian process regression is that outputs are jointly Gaussian distributed, so that

$$ P(y_p|y_t) \propto P(y_p,y_t) \propto \exp\left[-\frac{1}{2} \left(\begin{array}{c} y_t \\ y_p \end{array}\right)^T\Sigma^{-1}\left(\begin{array}{c} y_t \\ y_p \end{array}\right)\right] $$

Where $\Sigma$ is the joint covariance matrix. Remember that under the Gaussian process model we have trained a function which computes the elements of the Covariance matrix purely as a function of the inputs, it is only a function of the outputs $y_p$ that we're trying to find. We can define the covariance matrix blockwise

$$ \Sigma = \left(\begin{array}{cc} T & C^T \\ C & P \end{array}\right) $$

Where $T$ is the covariance matrix computed using only the training inputs $x_t$, $P$ is the covariance matrix computed using the prediction inputs $x_p$, and $C$ is the cross terms (i.e. the covariance \emph{between} $y_t$ and $y_p$, computed using $x_t$ and $x_p$). It is a well known result (it's in numerical recipes, or on Wikipedia) that you can blockwise invert a matrix;

$$ \Sigma^{-1} = \left(\begin{array}{cc}T^{-1} + T^{-1}C^T M CT^{-1} & -T^{-1}C^TM \\ -MCT^{-1} & M\end{array}\right) $$

Where $M = (P-CT^{-1}C^T)^{-1}$. So, we can directly compute our Gaussian density

\begin{align}
P(y_p|y_t) \propto \exp\Bigg[ & -\frac{1}{2} y_t^T(T^{-1} + T^{-1}C^T M CT^{-1})y_t \nonumber \\
& + \frac{1}{2}y_t^T (T^{-1}C^TM)y_p \nonumber \\
& + \frac{1}{2}y_p^T (MCT^{-1})y_t \nonumber \\
& - \frac{1}{2}y_p^TMy_p\Bigg] \nonumber
\end{align}

However, the only thing that isn't a constant here is $y_p$, so we can drop a bunch of terms (since we're only interested in the density, not absolute values)

$$ P(y_p|y_t) \propto \exp\left[\frac{1}{2}y_t^T (T^{-1}C^TM)y_p + \frac{1}{2}y_p^T (MCT^{-1})y_t - \frac{1}{2}y_p^TMy_p\right] $$

If we take the transpose of the middle term, we can group the terms together a bit more

$$ P(y_p|y_t) \propto \exp\left[\frac{1}{2}y_t^T (T^{-1}C^TM + (MCT^{-1})^T)y_p - \frac{1}{2}y_p^TMy_p\right] $$

Now, in general, a multivariate Gaussian has the form;

$$ \mathcal{N}(\tilde{y},\tilde{\Sigma}) \propto \exp\left[-\frac{1}{2}(y-\tilde{y})^T\tilde{\Sigma}^{-1}(y-\tilde{y})\right] $$

If we remember that covariance matrices are symmetric, we can expand, drop some constant terms and then rearrange this to

$$ \mathcal{N}(\tilde{y},\tilde{\Sigma}) \propto \exp\left[-\frac{1}{2}y^T\tilde{\Sigma}^{-1}y + \tilde{y}^T\tilde{\Sigma}^{-1}y\right] $$

we can therefore see that both $P(y_p|y_t)$ and $\mathcal{N}(\tilde{y},\tilde{\Sigma})$ have exactly the same form. We can therefore straightforwardly match expressions for $\tilde{\Sigma}$.

$$ \tilde{\Sigma} = M^{-1} = P-CT^{-1}C^T $$

The expression for $\tilde{y}$ requires a little more work. We start by matching terms

$$ \tilde{y}^T\tilde{\Sigma}^{-1} = \frac{1}{2}y_t^T (T^{-1}C^TM + (MCT^{-1})^T) $$

We can rearrange this a little bit

$$ \tilde{y}^T\tilde{\Sigma}^{-1} = \frac{1}{2}y_t^T T^{-1}C^T (M + M^T) $$

We know that $M$ is a symmetric matrix (we just showed that its inverse is the covariance matrix). So, if we right multiply by the covariance matrix $\tilde{\Sigma}$ and take the transpose, we finally arrive at

$$\tilde{y} = CT^{-1}y_t $$

And, so, in conclusion we know that

$$P(y_p|y_t) \sim \mathcal{N}(CT^{-1}y_t, P-CT^{-1}C^T) $$

So, not quite as trivial as the textbooks claim!
