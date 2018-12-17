"""
Created on December 15, 2018

@author: clvoloshin, 
"""

from fitted_algo import FittedAlgo
from model import Model
import numpy as np
from tqdm import tqdm
import scipy.signal as signal

class InversePropensityScorer(object):
    def __init__(self, action_space_dim):
        '''
        An implementation of fitted Q iteration

        num_inputs: number of inputs
        dim_of_actions: dimension of action space
        max_epochs: positive int, specifies how many iterations to run the algorithm
        gamma: discount factor
        '''
        self.action_space_dim = action_space_dim
        # self.initial_states = initial_states

    def run(self, *args):
        '''
        V^pi(s) = sum_{i = 1}^n p(h_j| pi_new, s_0 = s)/p(h_j| pi_old, s_0 = s) H(h_j)
        h = (s_1, a_1, r_1, s_2, ...)
        p(h_j | pi, s) = pi(a_0 | s_0)p(r_0 | s_0, a_0)p(s_1 | s_0, a_0)pi(a_1 |s_1) ...
                       = prod_j pi(a_j | x_j)p(r_j | x_j, a_j)p(s_{j+1} | x_j, a_j)
        deterministic  = prod_j pi(a_j | x_j) * 1 * 1 
                       = prod_j pi(a_j | x_j)
        H(h_j) = r_0 + gamma * r_1 + gamma^2 r_2 + ...
        
        '''


        approx_ips = self.approx_ips(*args)
        exact_ips = self.exact_ips(*args)
        approx_pdis = self.approx_pdis(*args)
        exact_pdis = self.exact_pdis(*args)

        return approx_ips, exact_ips, approx_pdis, exact_pdis

    def approx_pdis(self, dataset, pi_new, pi_old, epsilon, gamma):
        '''
        Per decision importance sampling

        sum_{t=1}^{max L} gamma^t  1/n sum_{i=1}^n (PI_{tau=1}^t p_new/p_old) R^i_t
        '''
        
        pi_new_a_given_x = [(pi_new(episode['x']) == episode['a']).astype(float) for episode in dataset.episodes]

        # approx IPS, pi_old_a_given_x is approximated by the dataset
        actions = np.eye(self.action_space_dim)[dataset['a']]
        unique_states_seen = np.unique(dataset['x'])
        probabilities = [np.mean(actions[dataset['x'] == x], axis=0) for x in unique_states_seen]

        prob = {}
        for idx, state in enumerate(unique_states_seen):
            prob[state] = probabilities[idx]

        pi_old_a_given_x = [[ prob[x][a]  for x,a in episode['state_action']] for episode in dataset.episodes]

        pi_new_cumprod = np.array([np.pad(np.cumprod(x), (0,dataset.get_max_trajectory_length()-len(x)), 'constant', constant_values=(0,0)) for x in pi_new_a_given_x])
        pi_old_cumprod = np.array([np.pad(np.cumprod(x), (0,dataset.get_max_trajectory_length()-len(x)), 'constant', constant_values=(0,1)) for x in pi_old_a_given_x])
        costs = [episode['cost'] for episode in dataset.episodes]
        costs = np.array([np.pad(x, (0,dataset.get_max_trajectory_length()-len(x)), 'constant', constant_values=(0,0)) for x in costs])

        return self.discounted_sum(np.mean(pi_new_cumprod / pi_old_cumprod * costs, axis=0), gamma)

        # pi_new_cumprod = [np.cumprod(x) for x in pi_new_a_given_x]
        # pi_old_cumprod = [np.cumprod(x) for x in pi_old_a_given_x]
        # costs = [episode['cost'] for episode in dataset.episodes]

        # per_decision = []
        # for i in range(dataset.get_max_trajectory_length()):
        #     s = 0
        #     count = 0
        #     for trajectory in range(len(costs)):
        #         try:
        #             s += pi_new_cumprod[trajectory][i] / pi_old_cumprod[trajectory][i] * costs[trajectory][i]
        #             count += 1
        #         except:
        #             pass
        #     per_decision.append(s/float(count))


        # return self.discounted_sum(per_decision, gamma)

    def exact_pdis(self, dataset, pi_new, pi_old, epsilon, gamma):
        '''
        Per decision importance sampling

        sum_{t=1}^{max L} gamma^t  1/n sum_{i=1}^n (PI_{tau=1}^t p_new/p_old) R^i_t
        '''
        
        pi_new_a_given_x = [(pi_new(episode['x']) == episode['a']).astype(float) for episode in dataset.episodes]
        pi_old_a_given_x = [(pi_old(episode['x']) == episode['a'])*(1-epsilon) + (1./self.action_space_dim)*epsilon for episode in dataset.episodes]

        pi_new_cumprod = np.array([np.pad(np.cumprod(x), (0,dataset.get_max_trajectory_length()-len(x)), 'constant', constant_values=(0,0)) for x in pi_new_a_given_x])
        pi_old_cumprod = np.array([np.pad(np.cumprod(x), (0,dataset.get_max_trajectory_length()-len(x)), 'constant', constant_values=(0,1)) for x in pi_old_a_given_x])
        costs = [episode['cost'] for episode in dataset.episodes]
        costs = np.array([np.pad(x, (0,dataset.get_max_trajectory_length()-len(x)), 'constant', constant_values=(0,0)) for x in costs])

        return self.discounted_sum(np.mean(pi_new_cumprod / pi_old_cumprod * costs, axis=0), gamma)

        # pi_new_cumprod = [np.cumprod(x) for x in pi_new_a_given_x]
        # pi_old_cumprod = [np.cumprod(x) for x in pi_old_a_given_x]
        # costs = [episode['cost'] for episode in dataset.episodes]

        # per_decision = []
        # for t in range(dataset.get_max_trajectory_length()):
        #     s = 0
        #     count = 0
        #     for trajectory in range(len(costs)):
        #         try:
        #             s += pi_new_cumprod[trajectory][t] / pi_old_cumprod[trajectory][t] * costs[trajectory][t]
        #             count += 1
        #         except:
        #             pass
        #     per_decision.append(s/count)

        # return self.discounted_sum(per_decision, gamma)

    def approx_ips(self, dataset, pi_new, pi_old, epsilon, gamma):
        '''
        Inverse propensity scoring (Importance sampling)
        '''
        H_h_j = [self.discounted_sum(episode['cost'], gamma) for episode in dataset.episodes]
        pi_new_a_given_x = [(pi_new(episode['x']) == episode['a']).astype(float) for episode in dataset.episodes]

        # approx IPS, pi_old_a_given_x is approximated by the dataset
        actions = np.eye(self.action_space_dim)[dataset['a']]
        unique_states_seen = np.unique(dataset['x'])
        probabilities = [np.mean(actions[dataset['x'] == x], axis=0) for x in unique_states_seen]

        prob = {}
        for idx, state in enumerate(unique_states_seen):
            prob[state] = probabilities[idx]

        pi_old_a_given_x = [[ prob[x][a]  for x,a in episode['state_action']] for episode in dataset.episodes]

        approx_ips= 0
        for i in range(len(H_h_j)):
            prob_new = np.prod(pi_new_a_given_x[i])
            prob_old = np.prod(pi_old_a_given_x[i])
            if (prob_new > 0) and (prob_old == 0):
                return np.inf
            approx_ips += prob_new/prob_old * H_h_j[i]

        if np.isnan(approx_ips):
            approx_ips = np.inf
        else:
            approx_ips /= len(H_h_j)

        return approx_ips


    def exact_ips(self, dataset, pi_new, pi_old, epsilon, gamma):
        H_h_j = [self.discounted_sum(episode['cost'], gamma) for episode in dataset.episodes]
        pi_new_a_given_x = [(pi_new(episode['x']) == episode['a']).astype(float) for episode in dataset.episodes]

        # exact IPS. If you know pi_old, can calculate exactly
        pi_old_a_given_x = [(pi_old(episode['x']) == episode['a'])*(1-epsilon) + (1./self.action_space_dim)*epsilon for episode in dataset.episodes]

        exact_ips = 0
        for i in range(len(H_h_j)):
            prob_new = np.prod(pi_new_a_given_x[i])
            prob_old = np.prod(pi_old_a_given_x[i])
            if (prob_new > 0) and (prob_old == 0):
                return np.inf
            exact_ips += prob_new/prob_old * H_h_j[i]

        
        if np.isnan(exact_ips):
            exact_ips = np.inf
        else:
            exact_ips /= len(H_h_j)

        return exact_ips


    @staticmethod
    def discounted_sum(costs, discount):
        '''
        Calculate discounted sum of costs
        '''
        y = signal.lfilter([1], [1, -discount], x=costs[::-1])
        return y[::-1][0]
