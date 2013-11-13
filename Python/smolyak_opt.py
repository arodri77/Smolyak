"""
This file contains a class that builds a Smolyak Grid.  The hope is that
it will eventually contain the interpolation routines necessary so that
the given some data, this class can build a grid and use the Chebyshev
polynomials to interpolate and approximate the data.

Method based on Judd, Maliar, Maliar, Valero 2013 (W.P)

Authors: Chase Coleman and Spencer Lyon

"""
import sys
from operator import mul
from itertools import product, combinations_with_replacement
from itertools import chain
import numpy as np
from scipy.linalg import lu
import matplotlib.pyplot as plt
import pandas as pd
from mpl_toolkits.mplot3d import Axes3D
from smolyak_utils import *


class SmolyakGrid(object):
    """
    This class currently takes a dimension and a degree of polynomial
    and builds the Smolyak Sparse grid.  We base this on the work by
    Judd Maliar Maliar and Valero.  Hope to obtain speed ups beyond
    what they achieved.

    Attributes:
    ------------------
    d : scalar : integer
        This is the dimension of grid that you are building

    mu : scalar : integer
        mu is a parameter that defines the fineness of grid that we
        want to build


    Methods:
    --------

    a_chain : This builds the disjoint sets of basis points

    _s_n : This builds the joint set of all basis points

    _smol_inds : This constructs the indices that satisfy the
                      constraint d <= |i| <= d + mu

    build_grid : This method builds the sparse grid

    phi_chain : Builds the disjoint sets of basis polynomials subscripts
                 (1, 2) = \phi_1 \phi_2 etc...

    poly_inds : Combines the basis polynomials in a similar
                              fashion as build_grid wrt to points

    build_B : Builds the B matrix that will be used to interpolate

    plot_grid : Pretty obvious the function of this method... Plots grid

    Attributes:
    -----------

    d::Int  # number of dimensions
    mu::Int  # density parameter
    grid::Matrix{Float64}  # Smolyak grid
    inds::Array{Any, 1}  # Smolyak indices
    B::Matrix{Float64}  # matrix representing interpoland
    B_L::Matrix{Float64}  # L from LU decomposition of B
    B_U::Matrix{Float64}  # U from LU decomposition of B

    """

    def __init__(self, d, mu, do="all"):
        """
        Parameters
        ----------
        d : scalar : integer
            This is the dimension of grid that you are building

        mu : scalar : integer
            mu is a parameter that defines the fineness of grid that we
            want to build

        do : string : string
            do specifies whether you just want to build the grid or
            whether it should build the whole object.  Only takes values
            of "all" or "grid".  Default is "all"
        """
        self.d = d
        self.mu = mu

        if mu < 1:
            raise ValueError('The parameter mu needs to be > 1.')

        if d <= 1:
            raise ValueError('You are trying to build a one dimensional\
                             grid.')

        self.build_grid()
        if do == "all":
            self.build_B()

    def __repr__(self):
        msg = "Smolyak Grid:\n\td: {0} \n\tmu: {1} \n\tnpoints: {2}"
        return msg.format(self.d, self.mu, self.grid.shape[0])

    def __str__(self):
        return str(self.__repr__)

    def a_chain(self, n):
        """
        This method finds all of the unidimensional disjoint sets
        that we will use to construct the grid.  It improves on
        past algorithms by noting that A_{n} = S_{n}[evens] except for
        A_1 = {0} and A_2 = {-1, 1}. Additionally, A_{n} = A_{n+1}[odds]
        This prevents the calculation of these nodes repeatedly.  Thus
        we only need to calculate biggest of the S_n's to build the
        sequence of A_n's

        """

        # # Start w finding the biggest Sn(We will subsequently reduce it)
        Sn = self._s_n(n)

        A_chain = {}
        A_chain[1] = [0.]
        A_chain[2] = [-1., 1.]

        # Need a for loop to extract remaining elements
        for seq in xrange(n, 2, -1):
            num = Sn.size
            # Need odd indices in python because indexing starts at 0
            A_chain[seq] = tuple(Sn[range(1, num, 2)])
            # A_chain.append(list(Sn[range(1, num, 2)]))
            Sn = Sn[range(0, num, 2)]

        return A_chain

    def _s_n(self, n):
        """
        This method finds the element S_n for the Chebyshev Extrema
        """

        if n == 1:
            return np.array([0.])

        # Apply the necessary transformation to get the nested sequence
        m_i = 2**(n-1) + 1

        # Create an array of values that will be passed in to calculate
        # the set of values
        comp_vals = np.arange(1., m_i + 1.)

        # Values are - cos(pi(j-1)/(n-1)) for j in [1, 2, ..., n]
        vals = -1. * np.cos(np.pi*(comp_vals - 1.)/(m_i-1.))
        vals[np.where(np.abs(vals) < 1e-14)] = 0.0

        return vals

    def _smol_inds(self):
        """
        This method finds all of the indices that satisfy the requirement
        that d \leq \sum_{i=1}^d \leq d + \mu.  Once we have these, then
        they can be used to build both the grid and the polynomial
        basis.

        Notes
        =====
        This method sets the attribute smol_inds
        """
        d = self.d
        mu = self.mu

        # Need to capture up to value mu + 1 so in python need mu+2
        possible_values = range(1, mu + 2)

        # find all (i1, i2, ... id) such that their sum is in range
        # we want; this will cut down on later iterations
        poss_inds = [el for el in combinations_with_replacement(possible_values, d)
                      if d < sum(el) <= d+mu]

        true_inds = [[el for el in permute(list(val))] for val in poss_inds]

        # Add the d dimension 1 array so that we don't repeat it a bunch
        # of times
        true_inds.extend([[[1]*d]])

        tinds = list(chain.from_iterable(true_inds))

        self.smol_inds = tinds

        return tinds

    def build_grid(self):
        """
        This method builds a grid for the object

        Notes
        =====
        This method sets the attribute grid
        """
        mu = self.mu

        # Get An chain
        An = self.a_chain(mu + 1)

        points = []

        # Need to get the correct indices

        tinds = self._smol_inds()

        for el in tinds:
            temp = [An[i] for i in el]
            # Save these indices that we iterate through because
            # we need them for the chebyshev polynomial combination
            # inds.append(el)
            points.extend(list(product(*temp)))

        grid = pd.lib.to_object_array_tuples(points).astype(float)
        self.grid = grid

        return grid

    def phi_chain(self, n):
        """
        Finds the disjoint sets of aphi's that will be used to compute
        which functions we need to calculate
        """

        # First create a dictionary
        aphi_chain = {}

        aphi_chain[1] = [1]
        aphi_chain[2] = [2, 3]

        curr_val = 4
        for i in xrange(3, n+1):
            end_val = 2**(i-1) + 1
            temp = range(curr_val, end_val+1)
            aphi_chain[i] = temp
            curr_val = end_val+1

        return aphi_chain

    def poly_inds(self):
        """
        This function builds the indices of the basis polynomials that
        will be used to interpolate.
        """
        mu = self.mu

        smol_inds = self.smol_inds
        aphi = self.phi_chain(mu + 1)

        # Bring in polynomials
        # cheb_dict = self.calc_chebvals()

        base_polys = []

        for el in smol_inds:
            temp = [aphi[i] for i in el]
            # Save these indices that we iterate through because
            # we need them for the chebyshev polynomial combination
            # inds.append(el)
            base_polys.extend(list(product(*temp)))

        return base_polys

    def build_B(self):
        """
        This function builds the matrix B that will be used to calc
        the interpolation coefficients for a given set of data.

        Notes
        =====
        This method sets the attributes B, B_L, B_U
        """
        Ts = cheby2n(self.grid.T, m_i(self.mu + 1))
        base_polys = self.poly_inds()
        n = len(self.grid)
        B = np.empty((n, n), order='F')
        for ind, comb in enumerate(base_polys):
            B[:, ind] = reduce(mul, [Ts[comb[i] - 1, i, :]
                               for i in range(self.d)])
        self.B = B

        # Compute LU decomposition
        l, u = lu(B, True)  # pass permute_l as true. See scipy docs
        self.B_L = l
        self.B_U = u

        return B

    def plot_grid(self):
        grid = self.grid
        if grid.shape[1] == 2:
            xs = grid[:, 0]
            ys = grid[:, 1]
            fig = plt.figure()
            ax = fig.add_subplot(111)
            ax.scatter(xs, ys)
            ax.grid(True, linestyle='--', color='0.75')
            plt.show()
        elif grid.shape[1] == 3:
            xs = grid[:, 0]
            ys = grid[:, 1]
            zs = grid[:, 2]
            fig = plt.figure()
            ax = fig.add_subplot(111, projection='3d')
            ax.scatter(xs, ys, zs)
            ax.grid(True, linestyle='--', color='0.75')
            plt.show()
        else:
            raise ValueError('Can only plot 2 or 3 dimensional problems')


my_args = sys.argv[1:]

if __name__ == '__main__':

    for d, mu in [(20, 2), (10, 3), (20, 3)]:
        s = SmolyakGrid(d, mu, do="grid")
        print(s.build_grid().shape, num_grid_points(d, mu))

if 'prof' in my_args or 'profile' in my_args:
    import cProfile
    cProfile.run("s.build_grid()")
    cProfile.run("smm.smolyak_grids(d, mu)")
