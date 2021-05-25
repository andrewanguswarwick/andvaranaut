#!/bin/python3

from andvaranaut.utils import _core
from andvaranaut.forward import GP
import numpy as np
from scipy.optimize import differential_evolution
import scipy.stats as st
import copy
import GPy
from scipy.misc import derivative

# Maximum a posteriori class
class MAP(_core):
  def __init__(self,nx_exp,nx_model,**kwargs):
    # Check inputs
    if (not isinstance(nx_exp,int)) or (nx_exp < 0):
      raise Exception(\
          'Error: must specify an integer number of experimental input parameters => 0') 
    if (not isinstance(nx_model,int)) or (nx_model < 1):
      raise Exception('Error: must specify an integer number of model input parameters > 0') 
    # Allow for only specifying priors for model parameters
    if (isinstance(kwargs['priors'],list)) and (len(kwargs['priors']) == nx_model):
      for i in range(nx_exp):
        kwargs['priors'].insert(0,st.norm())
    super().__init__(nx=nx_exp+nx_model,**kwargs)
    # Initialise new attributes
    self.nx_exp = nx_exp # Observable input dimensions
    self.nx_model = nx_model # Model input dimensions
    self.x_obv = None
    self.y_obv = None
    self.y_noise = None
    self.obvs = None
    self.x_opt = None

  # Set your experimental x and y with noise
  def set_observations(self,y,y_noise=None,x_exp=None):
    # Check y input
    if not isinstance(y,np.ndarray) or len(y.shape) != 2 \
        or y.dtype != 'float64' or y.shape[1] != self.ny:
      raise Exception(\
          "Error: Setting data requires a 2d numpy array of float64 outputs")
    # Check/modify other inputs
    self.obvs = len(y)
    if y_noise is None:
      y_noise = np.ones((self.obvs,self.ny))*np.finfo(np.float64).eps
    else:
      if not isinstance(y_noise,np.ndarray) or len(y_noise.shape) != 2 \
          or y_noise.dtype != 'float64' or y_noise.shape[1] != self.ny:
        raise Exception(\
            "Error: Setting data requires a 2d numpy array of float64 noises"+\
            " of the same shape as y")
    if x_exp is None:
      if self.nx_exp != 0:
        raise Exception("Error: must provide x_exp values for each observation")
    else:
      if not isinstance(x_exp,np.ndarray) or len(x_exp.shape) != 2 \
          or x_exp.dtype != 'float64' or x_exp.shape[1] != self.nx_exp:
        raise Exception(\
            "Error: Setting data requires a 2d numpy array of float64 exp inputs"+\
            " of shape (len(y),nx_exp)")
    # Set obvs
    self.x_obv = np.zeros((self.obvs,self.nx))
    self.x_obv[:,:self.nx_exp] = x_exp
    self.y_obv = y
    self.y_noise = y_noise

  # Log prior method acting on specified model inputs
  def log_prior(self,x):
    logps = np.zeros(self.nx_model)
    for i in range(self.nx_model):
      logps[i] = self.priors[i+self.nx_exp].logpdf(x[i])
    return np.sum(logps)

  # Gaussian log likelihood method acting on specified model inputs
  def log_likelihood(self,x):
    self.x_obv[:,self.nx_exp:] = x
    xsamps,fvals = self._core__vector_solver(self.x_obv,verbose=False)
    if len(xsamps) != self.obvs:
      raise Exception("Error: one or more function evaluations failed to return valid result.")
    res = -self.obvs*self.ny*0.5*np.log(2*np.pi)
    res -= np.sum(np.log(self.y_noise))
    res -= np.sum(0.5/np.power(self.y_noise,2)*np.power(fvals-self.y_obv,2))
    return res

  # Log posterior method acting on specified model inputs
  def log_posterior(self,x):
    return self.log_likelihood(x) + self.log_prior(x)

  # Negative version of log posterior for minimizing using standard libraries
  def __negative_log_posterior(self,x):
    return -self.log_posterior(x)
    
  def opt(self):
    # Bounds which try and avoid extrapolation
    bnd = 0.999999999999999
    bnds = tuple(self.priors[i+self.nx_exp].interval(bnd) for i in range(self.nx_model))
    print("Finding optimal inputs by maximising posterior. Bounds on x are:")
    print(bnds)
    res = differential_evolution(self.__negative_log_posterior,bounds=bnds)
    self.xopt = res.x

    print(f'Optimal converted model parameters are: {res.x}')
    print(f'Posterior is: {-res.fun:0.3f}')

# MAP class using a GP
class GPMAP(MAP,GP):
  def __init__(self,nx_exp,nx_model,\
          kernel='RBF',noise=True,xconrevs=None,yconrevs=None,**kwargs):
    # Init of two parent classes
    super().__init__(nx_exp=nx_exp,nx_model=nx_model,**kwargs)
    kwargs['nx'] = self.nx
    GP.__init__(self,kernel=kernel,noise=noise,xconrevs=xconrevs,yconrevs=yconrevs,**kwargs)

    # Additional check on priors to make sure both nx_exp and nx_model represented
    if len(self.priors) != len(kwargs['priors']):
      raise Exception(\
          'Error: must provide list of scipy.stats univariate priors of length nx') 

    # Initialise new attributes
    self.yc_obv = None
    self.xc_obv = None
    self.yc_noise = None
    self.xcopt = None

  # Allow for setting attributes with existing GP class from andvaranaut.forward
  def set_GP(self,gp):
    # Check inputs
    if (not isinstance(gp,GP)):
      raise Exception("Error: must provide gp class instance from andvaranaut.forward module")
    if (self.nx != gp.nx):
      raise Exception("Error: nx_exp and nx_model must sum to gp.nx")
    if (self.ny != gp.ny):
      raise Exception("Error: self.ny does not match gp.ny")
    print("Warning: Setting GP overwrites GPMAP init arguments. Ensure priors etc. are correct.")
    # Extract attributes
    self.priors = gp.priors
    self.target = gp.target
    self.parallel = gp.parallel
    self.nproc = gp.nproc
    self.xtrain = gp.xtrain
    self.xtest = gp.xtest
    self.ytrain = gp.ytrain
    self.ytest = gp.ytest
    self.kernel = gp.kernel
    self.noise = gp.noise
    self.m = gp.m
    self.x = gp.x
    self.y = gp.y
    self.xconrevs = gp.xconrevs
    self.yconrevs = gp.yconrevs
    self.xc = gp.xc
    self.yc = gp.yc
    # Reset observations to ensure correct conversions if already set
    if self.y_obv is not None:
      self.set_observations(self.y_obv,self.y_noise,self.x_obv[:,:self.nx_exp])

  # Extend parent method to include data conversion/reversion
  def set_observations(self,y,y_noise=None,x_exp=None):
    super().set_observations(y,y_noise,x_exp)
    self.yc_obv = copy.deepcopy(self.y_obv)
    self.xc_obv = copy.deepcopy(self.x_obv)
    self.yc_noise = copy.deepcopy(self.y_noise)
    for i in range(self.nx_exp):
      self.xc_obv[:,i] = self.xconrevs[i].con(self.x_obv[:,i])
    for i in range(self.ny):
      self.yc_obv[:,i] = self.yconrevs[i].con(self.y_obv[:,i])
    for i in range(self.ny):
      self.yc_noise[:,i] = self.yconrevs[i].con(self.y_noise[:,i])

  # Private method which calculates Jacobian of x transform
  def __xder(self,x,i):
    return derivative(self.xconrevs[self.nx_exp+i].rev,x[i],dx=1e-6)

  # Extend log_prior method to work with converted priors
  def log_prior(self,x):
    logpsum = 0
    for i in range(self.nx_model):
      logpsum += np.log(self.__xder(x,i)) + \
          self.priors[self.nx_exp+i].logpdf(self.xconrevs[self.nx_exp+i].rev(x[i]))    
      return logpsum

  # Take log_likelihood from GP
  ## ToDo: Add option to also optimise hyperparameters
  def log_likelihood(self,x):
    xc = np.r_[self.xc,self.x_obv]
    yc = np.r_[self.yc,self.y_obv]
    xc[-self.obvs:,self.nx_exp:] = x
    kern = GPy.kern.Exponential(input_dim=nvars, ARD=True)
    kstring = 'GPy.kern.'+self.kernel+'(input_dim=self.nx,variance=1.,lengthscale=1.,ARD=True)'
    kern = eval(kstring)
    m = GPy.models.GPHeteroscedasticRegression(xc,yc,kern)
    m.kern.lengthscale = self.m.kern.lengthscale
    m.kern.variance = self.m.kern.variance
    m.Gaussian_noise.variance[:-self.obvs] = self.m.Gaussian_noise.variance
    m.Gaussian_noise.variance[-self.obvs:] = self.yc_noise
    return m.log_likelihood()

  # Method specific to this class which reverts posterior to original x coords for opt
  def __negative_rev_log_posterior(self,x):
    pc = self._MAP__negative_log_posterior(x)
    for i in range(self.nx_model):
      pc += np.log(self.__xder(x,i))
    return pc

  # Change opt method to use GP data bounds and reversion of optimised x values
  def opt(self):
    # Bounds which try and avoid extrapolation
    bnds = tuple((np.min(self.x[:,j]),np.max(self.x[:,j])) \
        for j in range(self.nx_exp,self.nx))
    print("Finding optimal model inputs by maximising posterior. Bounds on x are:")
    print(bnds)
    res = differential_evolution(self.__negative_rev_log_posterior,bounds=bnds)
    resx = np.zeros(self.nx_model)
    for i in range(self.nx_model):
      resx[i] = self.xconrevs[i+self.nx_exp].con(res.x[i])
    self.x_opt = resx
    self.xc_opt = res.x

    print(f'Optimal converted model parameters are: {res.x}')
    print(f'Reverted optimal model parameters are: {resx}')
    print(f'Posterior is: {-res.fun:0.3f}')

# Quick and dirty maximum a posteriori class using a GP
class gpmap:
  def __init__(self,nx_exp,nx_model,gp):
    # Check inputs
    if (not isinstance(nx_exp,int)) or (nx_exp < 0):
      raise Exception('Error: must specify an integer number of model input parameters => 0') 
    if (not isinstance(nx_model,int)) or (nx_model < 1):
      raise Exception('Error: must specify an integer number of model input parameters > 0') 
    if (not isinstance(gp,GP)):
      raise Exception("Error: must provide gp class instance from andvaranaut.forward module")
    if (nx_exp+nx_model != gp.nx):
      raise Exception("Error: nx_exp and nx_model must sum to gp.nx")

    # Initialise attributes
    self.nx_exp = nx_exp # Number of experimental inputs
    self.nx_model = nx_model # Number of model inputs
    self.gp = gp
    self.xopt = None
    self.xcopt = None
    self.yexp = None
    self.ycexp = None

  def set_y(self,y):
    self.xext = np.r_[self.gp.x,np.zeros((len(y),self.gp.nx))]
    self.yext = np.r_[self.gp.y,y]
    self.yexp = y
    for i in range(self.gp.nx):
      self.xext[:,i] = self.gp.xconrevs[i].con(self.xext[:,i])
    for i in range(self.gp.ny):
      self.yext[:,i] = self.gp.yconrevs[i].con(self.yext[:,i])
    self.ycexp = self.yext[-len(y):]

  def log_prior(self,x):
    logps = np.zeros(self.gp.nx)
    for i in range(self.gp.nx):
      logps[i] = self.gp.xconrevs[i].prior.logpdf(x[i])
    return np.sum(logps)

  def log_likelihood(self,x):
    gp2 = copy.deepcopy(self.gp)
    gp2.xc = self.xext
    gp2.xc[-1] = x
    gp2.yc = self.yext
    gp2.m = gp2._gp__fit(gp2.xc,gp2.yc,opt=False)
    gp2.m.kern.lengthscale = self.gp.m.kern.lengthscale
    gp2.m.kern.variance = self.gp.m.kern.variance
    gp2.m.Gaussian_noise.variance = self.gp.m.Gaussian_noise.variance
    return gp2.m.log_likelihood()

  def log_posterior(self,x):
    return self.log_likelihood(x) + self.log_prior(x)

  def __negative_log_posterior(self,x):
    return -self.log_posterior(x)
    
  def MAP(self):
    # Bounds which try and avoid extrapolation
    bnds = tuple((np.min(self.gp.xc[:,j]),np.max(self.gp.xc[:,j])) for j in range(self.gp.nx))
    print("Finding optimal inputs by maximising posterior. Bounds on xc are:")
    print(bnds)
    res = differential_evolution(self.__negative_log_posterior,bounds=bnds)
    resx = np.zeros(self.gp.nx)
    for i in range(self.gp.nx):
      resx[i] = self.gp.xconrevs[i].rev(res.x[i])
    self.xopt = resx
    self.xcopt = res.x

    print(f'Optimal converted model parameters are: {res.x}')
    print(f'Reverted optimal model parameters are: {resx}')
    print(f'Posterior is: {-res.fun:0.3f}')

# MCMC class inheriting from MAP
class mcmc(MAP):
  def __init__(self,**kwargs):
    super().__init__(**kwargs)

# GP-MCMC class inheriting from mcmc
class gpmcmc(mcmc):
  def __init__(self,gp,nx_exp,nx_model,**kwargs):
    super().__init__(**kwargs)
