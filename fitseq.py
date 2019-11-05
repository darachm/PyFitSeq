import numpy as np
import pandas as pd
import math
import argparse
import itertools
import csv
from scipy.stats import linregress
from scipy.optimize import minimize

read_num_seq_lineage_global = None
read_num_min_seq_lineage_global = None
read_depth_seq_global = None
t_seq_global = None
kappa_global = None
x_mean_global = None


def fun_estimate_parameters(x, read_num_seq, t_seq, kappa=2.5):
    # ------------------------------------------------------------------------------------------------------------------
    # A SUB-FUNCTION CALLED BY MAIN FUNCTION main() TO CALCULATE THE LOG LIKELIHOOD VALUE OF EACH GENOTYPE GIVEN ITS
    # FITNESS (WRIGHTIAN FITNESS), THE ESTIMATED READ NUMBER PER GENOTYPE PER SEQUENCING TIME-POINT, AND THE ESTIMATED
    # MEAN FITNESS PER SEQUENCING TIME-POINT
    #
    # INPUTS
    # --x: fitness of each genotype [x1, x2, ...]
    # --read_num_seq: read number per genotype per sequencing time-point
    # --t_seq: sequenced time-points [0, t1, t2, ...]
    # --kappa: a noise parameter that characterizes the total noise introduced by growth, cell transfer, DNA extraction,
    #          PCR, and sequencing. (To measure kappa empirically, see the reference: Levy et al. Nature 2015 519,
    #          181-186.) (default: 2.5)
    #
    # OUTPUTS
    # --estimate_parameters_output: log likelihood value of each genotype,
    #                               estimated reads number per genotype per sequencing time-point,
    #                               estimated mean fitness per sequencing time-point, [x_mean(t0),x_mean(t1),...]
    # ------------------------------------------------------------------------------------------------------------------
    read_num_seq = read_num_seq.astype(float)
    read_num_seq[read_num_seq == 0] = 1e-7
    read_depth_seq = np.sum(read_num_seq, axis=0)
    lineages_num, seq_num = read_num_seq.shape

    read_num_min_seq = np.zeros((lineages_num, seq_num))
    read_num_min_seq[:, 0] = read_num_seq[:, 0]
    for i in range(1, seq_num):
        read_num_min_seq[:, i] = read_num_min_seq[:, i - 1] / 2 ** (t_seq[i] - t_seq[i - 1])

    x[x <= -1] = -1 + 1e-7

    x_mean = np.zeros(seq_num)
    read_num_seq_est = np.zeros((lineages_num, seq_num))
    read_num_seq_est[:, 0] = read_num_seq[:, 0]
    likelihood_log_seq = np.zeros((lineages_num, seq_num))

    for i in range(1, seq_num):
        x_mean[i] = np.max(np.dot(x, read_num_seq[:, i]) / read_depth_seq[i], 0)

        read_num_est_tempt = np.exp((t_seq[i] - t_seq[i - 1]) * (np.log(1 + x) + 1)
                                    - (t_seq[i] - t_seq[i - 1]) / (x_mean[i] - x_mean[i - 1])
                                    * ((x_mean[i] + 1) * np.log(x_mean[i] + 1)
                                       - (x_mean[i - 1] + 1) * np.log(x_mean[i - 1] + 1)))

        read_num_est_tempt = read_num_est_tempt * read_num_seq[:, i - 1] / read_depth_seq[i - 1] * read_depth_seq[i]
        # read_num_est_tempt = read_num_est_tempt/np.sum(read_num_est_tempt)*read_depth_seq[i]
        read_num_seq_est[:, i] = np.max([read_num_est_tempt, read_num_min_seq[:, i]], axis=0)

        # x_mean[i] = np.dot(x, read_num_seq_est[:,i])/read_depth_seq[i]
        x_mean[i] = np.dot(x, read_num_seq_est[:, i]) / np.sum(read_num_seq_est[:, i])

    pos1_r, pos1_c = np.where(read_num_seq[:, :-1] >= 20)
    likelihood_log_seq[pos1_r, pos1_c + 1] = (0.25 * np.log(read_num_seq_est[pos1_r, pos1_c + 1])
                                              - 0.5 * np.log(4 * np.pi * kappa)
                                              - 0.75 * np.log(read_num_seq_est[pos1_r, pos1_c + 1])
                                              - (np.sqrt(read_num_seq[pos1_r, pos1_c + 1])
                                                 - np.sqrt(read_num_seq_est[pos1_r, pos1_c + 1])) ** 2 / kappa)

    pos_r, pos_c = np.where(read_num_seq[:, :-1] < 20)
    pos_p1 = np.where(read_num_seq[pos_r, pos_c + 1] >= 10)[0]
    pos_p2 = np.where(read_num_seq[pos_r, pos_c + 1] < 10)[0]
    pos2_r = pos_r[pos_p1]
    pos2_c = pos_c[pos_p1]
    pos3_r = pos_r[pos_p2]
    pos3_c = pos_c[pos_p2]

    likelihood_log_seq[pos2_r, pos2_c + 1] = (np.multiply(read_num_seq[pos2_r, pos2_c + 1],
                                                          np.log(read_num_seq_est[pos2_r, pos2_c + 1]))
                                              - read_num_seq_est[pos2_r, pos2_c + 1]
                                              - np.multiply(read_num_seq[pos2_r, pos2_c + 1],
                                                            np.log(read_num_seq[pos2_r, pos2_c + 1]))
                                              + read_num_seq[pos2_r, pos2_c + 1]
                                              - 0.5 * np.log(2 * np.pi * read_num_seq[pos2_r, pos2_c + 1]))

    factorial_tempt = [float(math.factorial(i)) for i in read_num_seq[pos3_r, pos3_c + 1].astype(int)]
    likelihood_log_seq[pos3_r, pos3_c + 1] = (np.multiply(read_num_seq[pos3_r, pos3_c + 1],
                                                          np.log(read_num_seq_est[pos3_r, pos3_c + 1]))
                                              - read_num_seq_est[pos3_r, pos3_c + 1]
                                              - np.log(factorial_tempt))

    likelihood_log = np.sum(likelihood_log_seq, axis=1)

    estimate_parameters_output = {'Likelihood_Log': likelihood_log,
                                  'Estimated_Read_Number': read_num_seq_est,
                                  'Estimated_Mean_Fitness': x_mean}

    return estimate_parameters_output


def fun_likelihood_lineage(x):
    # ------------------------------------------------------------------------------------------------------------------
    # A SUB-FUNCTION CALLED BY MAIN FUNCTION main() TO CALCULATE THE SUM OF THE NEGATIVE LOG LIKELIHOOD VALUE OF ALL
    # GENOTYPES GIVEN THE FITNESS OF EACH GENOTYPE (WRIGHTIAN FITNESS)
    #
    # INPUTS
    # --x: fitness of a genotype
    #
    # OUTPUTS
    # --output: the negative log likelihood value of the genotype
    # ------------------------------------------------------------------------------------------------------------------
    global read_num_seq_lineage_global
    global read_num_min_seq_lineage_global
    global read_depth_seq_global
    global t_seq_global
    global kappa_global
    global x_mean_global

    if x <= -1:
        x = -1 + 1e-7
    seq_num = read_num_seq_lineage_global.shape[0]
    read_num_seq_lineage_est = np.zeros(seq_num)
    read_num_seq_lineage_est[0] = read_num_seq_lineage_global[0]
    likelihood_log_seq_lineage = np.zeros(seq_num)

    for i in range(1, seq_num):
        read_num_lineage_est_tempt = np.exp((t_seq_global[i] - t_seq_global[i - 1]) * (np.log(1 + x) + 1)
                                            - (t_seq_global[i] - t_seq_global[i - 1]) / (
                                                    x_mean_global[i] - x_mean_global[i - 1])
                                            * ((x_mean_global[i] + 1) * np.log(x_mean_global[i] + 1)
                                               - (x_mean_global[i - 1] + 1) * np.log(x_mean_global[i - 1] + 1)))

        read_num_lineage_est_tempt = (read_num_lineage_est_tempt * read_num_seq_lineage_global[i - 1]
                                      / read_depth_seq_global[i - 1] * read_depth_seq_global[i])
        read_num_seq_lineage_est[i] = np.max([read_num_lineage_est_tempt, read_num_min_seq_lineage_global[i]])

    pos1 = np.where(read_num_seq_lineage_global[:-1] >= 20)[0]
    likelihood_log_seq_lineage[pos1 + 1] = (0.25 * np.log(read_num_seq_lineage_est[pos1 + 1])
                                            - 0.5 * np.log(4 * np.pi * kappa_global)
                                            - 0.75 * np.log(read_num_seq_lineage_est[pos1 + 1])
                                            - (np.sqrt(read_num_seq_lineage_global[pos1 + 1])
                                               - np.sqrt(read_num_seq_lineage_est[pos1 + 1])) ** 2 / kappa_global)

    pos = np.where(read_num_seq_lineage_global[:-1] < 20)[0]
    pos_p1 = np.where(read_num_seq_lineage_global[pos + 1] >= 10)[0]
    pos_p2 = np.where(read_num_seq_lineage_global[pos + 1] < 10)[0]
    pos2 = pos[pos_p1]
    pos3 = pos[pos_p2]
    likelihood_log_seq_lineage[pos2 + 1] = (np.multiply(read_num_seq_lineage_global[pos2 + 1],
                                                        np.log(read_num_seq_lineage_est[pos2 + 1]))
                                            - read_num_seq_lineage_est[pos2 + 1]
                                            - np.multiply(read_num_seq_lineage_global[pos2 + 1],
                                                          np.log(read_num_seq_lineage_global[pos2 + 1]))
                                            + read_num_seq_lineage_global[pos2 + 1]
                                            - 0.5 * np.log(2 * np.pi * read_num_seq_lineage_global[pos2 + 1]))

    factorial_tempt = [float(math.factorial(i)) for i in read_num_seq_lineage_global[pos3 + 1].astype(int)]
    likelihood_log_seq_lineage[pos3 + 1] = (np.multiply(read_num_seq_lineage_global[pos3 + 1],
                                                        np.log(read_num_seq_lineage_est[pos3 + 1]))
                                            - read_num_seq_lineage_est[pos3 + 1]
                                            - np.log(factorial_tempt))

    likelihood_log_lineage = np.sum(likelihood_log_seq_lineage)
    return -likelihood_log_lineage


def main():
    # ------------------------------------------------------------------------------------------------------------------
    # ESTIMATE FITNESS OF EACH GENOTYPE IN A COMPETITIVE POOLED GROWTH EXPERIMENT
    #
    # OPTIONS
    # --input: a .csv file, with each column being the read number per genotype at each sequencing time-point
    # --t_seq: sequenced time-points (format: 0 t1 t2 ...)
    # --max_iter_num: maximum number of iterations in the optimization (default: 10)
    # --kappa: a noise parameter that characterizes the total noise
    #           introduced by growth, cell transfer, DNA extraction, PCR, and sequencing.
    #           (To measure kappa empirically, see the reference: Levy et al. Nature 2015 519,
    #           181-186.) (default: 2.5)
    # --regression_num: number of points used in initial linear regression (default: 2)
    # --output_filename: prefix of output .csv files (default: output)
    #
    # OUTPUTS
    # output_filename_FitSeq_Result.csv: 1st column: estimated fitness of each genotype, [x1, x2, ...],
    #                                    2nd column: log likelihood value of each genotype, [f1, f2, ...],
    #                                    3rd column: estimated mean fitness per sequencing time-point
    #                                                [x_mean(0), x_mean(t1), ...],
    #                                    4th column: estimated reads number per genotype per sequencing time-point
    # ------------------------------------------------------------------------------------------------------------------
    global read_num_seq_lineage_global
    global read_num_min_seq_lineage_global
    global read_depth_seq_global
    global t_seq_global
    global kappa_global
    global x_mean_global

    parser = argparse.ArgumentParser(description='Estimate fitness of each genotype in a competitive pooled growth '
                                                 'experiment', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-i', '--input', type=str, help='a .csv file: with each column being the read number per '
                                                        'genotype at each sequencing time-point')
    parser.add_argument('-t', '--t_seq', nargs='*', type=int, help='sequenced time-points')
    parser.add_argument('-m', '--max_iter_num', type=int, default=10,
                        help='maximum number of iterations in the optimization')
    parser.add_argument('-k', '--kappa', type=float, default=2.5,
                        help='a noise parameter that characterizes the total noise introduced by growth, '
                             'cell transfer, DNA extraction, PCR, and sequencing. (To measure kappa empirically, '
                             'see the reference: Levy et al. Nature 2015 519, 181-186.)')
    parser.add_argument('-g', '--regression_num', type=int, default=2,
                        help='number of points used in initial linear regression')
    parser.add_argument('-o', '--output_filename', type=str, default='output', help='prefix of output .csv files')

    args = parser.parse_args()
    read_num_seq = np.array(pd.read_csv(args.input, header=None), dtype=float)
    t_seq = np.array(args.t_seq, dtype=int)
    max_iter_num = args.max_iter_num
    kappa = args.kappa
    regression_num = args.regression_num
    output_filename = args.output_filename

    read_num_seq[read_num_seq[:, 0] < 1] = 1
    read_num_seq[read_num_seq == 0] = 1e-7
    read_depth_seq = np.sum(read_num_seq, axis=0)
    lineages_num, seq_num = read_num_seq.shape
    read_num_min_seq = np.zeros((lineages_num, seq_num))
    read_num_min_seq[:, 0] = read_num_seq[:, 0]
    for i in range(1, seq_num):
        read_num_min_seq[:, i] = read_num_min_seq[:, i - 1] / 2 ** (t_seq[i] - t_seq[i - 1])

    read_freq_seq = read_num_seq / read_depth_seq
    if regression_num == 2:
        x0_tempt = np.power(np.true_divide(read_freq_seq[:, 1], read_freq_seq[:, 0]), 1 / (t_seq[1] - t_seq[0])) - 1
    else:
        x0_tempt = [regression_output.slope for i in range(lineages_num)
                    for regression_output in [linregress(t_seq[0:regression_num],
                                                         np.log(read_freq_seq[i, 0:regression_num]))]]
        x0_tempt = np.exp(x0_tempt) - 1

    x0 = (1 + x0_tempt) / (1 + np.dot(read_freq_seq[:, 0], x0_tempt)) - 1  # Normalization
    x_opt = (1 + x0_tempt) / (1 + np.dot(read_freq_seq[:, 0], x0_tempt)) - 1

    read_depth_seq_global = read_depth_seq
    t_seq_global = t_seq
    kappa_global = kappa
    parameter_output = fun_estimate_parameters(x0, read_num_seq, t_seq, kappa)
    x_mean_global = parameter_output['Estimated_Mean_Fitness']
    likelihood_log_sum_iter = [-1e50 * lineages_num, np.sum(parameter_output['Likelihood_Log'])]
    step_size = 1 / lineages_num
    iter_num = 0

    while (likelihood_log_sum_iter[-1] - likelihood_log_sum_iter[-2] >= step_size) and (iter_num <= max_iter_num):
        for i in range(lineages_num):
            x0_lineage = x_opt[i]
            read_num_seq_lineage_global = read_num_seq[i, :]
            read_num_min_seq_lineage_global = read_num_min_seq[i, :]
            opt_output_lineage = minimize(fun_likelihood_lineage, x0_lineage, method='BFGS',
                                          options={'disp': False, 'maxiter': 50})
            x_opt[i] = opt_output_lineage['x'][0]

        parameter_output = fun_estimate_parameters(x_opt, read_num_seq, t_seq, kappa)
        likelihood_log_sum_iter.append(np.sum(parameter_output['Likelihood_Log']))
        x_mean_global = parameter_output['Estimated_Mean_Fitness']
        iter_num += 1
        print('Iteration ' + str(iter_num) + ': ' + str(likelihood_log_sum_iter[-1]))

    read_num_seq_est = parameter_output['Estimated_Read_Number']
    x_opt = x_opt - np.dot(read_num_seq_est[:, 0], x_opt) / np.sum(read_num_seq_est[:, 0])
    # x_opt = (1+x_opt)/(1+np.dot(read_num_seq_est[:,0], x_opt)/np.sum(read_num_seq_est[:,0])) - 1
    parameter_output_final = fun_estimate_parameters(x_opt, read_num_seq, t_seq)
    x_mean_est = parameter_output_final['Estimated_Mean_Fitness']
    likelihood_log = parameter_output_final['Likelihood_Log']

    fitseq_output = {'Estimated_Fitness': x_opt,
                     'Likelihood_Log': likelihood_log,
                     'Estimated_Mean_Fitness': x_mean_est,
                     'Estimated_Read_Number': read_num_seq_est}

    tempt = list(itertools.zip_longest(*list(fitseq_output.values())))
    with open(output_filename + '_FitSeq.csv', 'w') as f:
        w = csv.writer(f)
        w.writerow(fitseq_output.keys())
        w.writerows(tempt)
    return fitseq_output


if __name__ == "__main__":
    main()
