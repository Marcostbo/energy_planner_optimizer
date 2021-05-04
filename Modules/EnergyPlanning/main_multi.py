# coding=utf-8

from Modules.PyHydro.mddh import mddh
from Modules.EnergyPlanning.pdde_sistema_equivalente import *
from Modules.WindScenariosGenerator.main_long import main as wind
from Modules.EnergyPlanning.sim_oper import Sim_Oper

from timeit import default_timer as timer
import matplotlib.pyplot as plt
import pandas as pd


def main(path_nw: str, path_wind: str, nr_months: int, altitude: int, nr_wind_series: int, method_wind_series: str, nr_ena_abert: int, nr_ena_series: int, submarket_codes: list, nr_process: int):

    # Modulo de configuração leitura do deck NEWAVE e modulo de calculo de energias
    sistema = mddh(path_nw)

    submarket_codes_all = [x.Codigo for x in sistema.submercado]
    submarket_index = [submarket_codes_all.index(i) for i in submarket_codes]

    # Parâmetros de entrada
    mes_ini = sistema.dger.MesInicioEstudo  # mes inicial
    ano_ini = sistema.dger.AnoInicioEstudo  # ano inicial

    # Gera cenários de energia eólica
    nr_wind_turbines = [166, 500, 833]
    rotor_area = 17860

    np.random.seed(1234)
    wind_scenarios = np.zeros((len(submarket_index), nr_wind_series, nr_months))
    for isist in range(len(submarket_index)):
        if submarket_codes[isist] == 3:
            wind_series = wind(path_wind=path_wind, altitude=altitude, nr_series=nr_wind_series, method=method_wind_series, sistema=sistema)
            for iser in range(nr_wind_series):
                wind_scenarios[isist, iser, :] = nr_wind_turbines[iser] * rotor_area * 0.5 * (1/1e6) *wind_series[1, mes_ini-1:mes_ini-1+nr_months]

    plt.plot(np.arange(1, nr_months+1), wind_scenarios[2][0], label='Pessimista', color='red')
    plt.plot(np.arange(1, nr_months+1), wind_scenarios[2][1], label='Regular', color='blue')
    plt.plot(np.arange(1, nr_months+1), wind_scenarios[2][2], label='Otimista', color='green')
    plt.xlabel('Estágio [meses]')
    plt.ylabel('Energia [MWmed]')
    plt.xticks(np.arange(1, nr_months+1))
    plt.xlim([1, nr_months])
    plt.legend(bbox_to_anchor=(0.13, -0.22, 0.8, 0.8), ncol=3)
    plt.show()

    # Gera aberturas e cenários de afluência
    aberturas = np.zeros((len(submarket_index), nr_ena_abert, nr_months))
    submercados = [sistema.submercado[i] for i in submarket_index]
    for idx, submercado in enumerate(submercados):
        submercado.parp(dados=submercado.ENA[:-2, :], ord_max=6)
        submercado.gera_series_sinteticas_sem_tendencia(dados=submercado.ENA[:-2, :], nr_ser=nr_ena_abert, plot=False)
        aberturas[idx] = submercado.series_sinteticas[:, mes_ini-1:mes_ini-1+nr_months]

    cenarios = np.zeros((nr_ena_series, nr_months))
    for icen in range(nr_ena_abert):
        cenarios[icen, :] = icen
    cont = nr_ena_abert
    while cont < nr_ena_series:
        values = np.random.randint(0, nr_ena_abert, nr_months)
        condition = True
        for row in cenarios[:cont, :]:
            if all(values == row):
                condition = False
                break
        if condition:
            cenarios[cont, :] = values
            cont += 1

    afluencias = np.zeros((len(submarket_index), nr_ena_series, nr_months))
    for isist in range(len(submarket_index)):
        for icen in range(nr_ena_series):
            for imes in range(nr_months):
                afluencias[isist, icen, imes] = aberturas[isist, int(cenarios[icen, imes]), imes]

    # Calcula os pesos das aberturas
    pesos_aber = np.zeros((nr_months, nr_ena_abert))
    for imes in range(nr_months):
        for iaber in range(nr_ena_abert):
            cen_afl = [cenarios[icen][imes] for icen in range(nr_ena_series)]
            rep = len([i for i in cen_afl if i == iaber])
            pesos_aber[imes, iaber] = rep/nr_ena_series
    pesos_eol = (1 / nr_wind_series) * np.ones((1, nr_wind_series))

    # TODO: Caso PL-MC
    # Política Operação
    t = timer()
    politica = pdde_SistMult(sistema, nr_months, aberturas, pesos_aber, afluencias, wind_scenarios, pesos_eol,
                               submarket_index, nr_process)
    politica.run_parallel()
    time = round((timer() - t) / 60, 2)
    politica.plot_convergencia(time=time, processos=nr_process)

    # Simulação da Operação
    simulacao = Sim_Oper(sistema, nr_months, afluencias, wind_scenarios, politica.cf, submarket_index, nr_process)
    simulacao.run()

    # TODO: Caso PL-UC (Pessimista)
    # Política Operação
    t = timer()
    wind_pessimista = wind_scenarios[:, 0, :].reshape(len(submarket_index), 1, nr_months)
    politica_P = pdde_SistMult(sistema, nr_months, aberturas, pesos_aber, afluencias, wind_pessimista, np.ones((1, 1)), submarket_index, nr_process)
    politica_P.run_parallel()
    time = round((timer() - t) / 60, 2)
    politica_P.plot_convergencia(time=time, processos=nr_process)

    # Simulação da Operação
    simulacao_P = Sim_Oper(sistema, nr_months, afluencias, wind_scenarios, politica_P.cf, submarket_index, nr_process)
    simulacao_P.run()

    # TODO: Caso PL-UC (Regular)
    # Política Operação
    t = timer()
    wind_regular = wind_scenarios[:, 1, :].reshape(len(submarket_index), 1, nr_months)
    politica_R = pdde_SistMult(sistema, nr_months, aberturas, pesos_aber, afluencias, wind_regular, np.ones((1, 1)),
                               submarket_index, nr_process)
    politica_R.run_parallel()
    time = round((timer() - t) / 60, 2)
    politica_R.plot_convergencia(time=time, processos=nr_process)

    # Simulação da Operação
    simulacao_R = Sim_Oper(sistema, nr_months, afluencias, wind_scenarios, politica_R.cf, submarket_index, nr_process)
    simulacao_R.run()

    # TODO: Caso PL-UC (Otimista)
    # Política Operação
    t = timer()
    wind_otimista = wind_scenarios[:, 2, :].reshape(len(submarket_index), 1, nr_months)
    politica_O = pdde_SistMult(sistema, nr_months, aberturas, pesos_aber, afluencias, wind_otimista, np.ones((1, 1)),
                               submarket_index, nr_process)
    politica_O.run_parallel()
    time = round((timer() - t) / 60, 2)
    politica_O.plot_convergencia(time=time, processos=nr_process)

    # Simulação da Operação
    simulacao_O = Sim_Oper(sistema, nr_months, afluencias, wind_scenarios, politica_O.cf, submarket_index, nr_process)
    simulacao_O.run()

    print('teste')

    serie_ena = 1
    # Export values to excel
    cenarios_eolicos = ['Pessimista', 'Regular', 'Otimista']
    for icen, cen in enumerate(cenarios_eolicos):

        values = np.zeros((48, nr_months))
        index = []
        columns = [i for i in range(1, nr_months+1)]
        cont = 0
        for isist, sist in enumerate(simulacao.resultados[icen].Sist):

            values[cont, :] = sist.GHidr[serie_ena, :]
            index.append(f'Geração Hidrelétrica_{sist.Nome}')

            values[cont+1, :] = sist.GTerm[serie_ena, :]
            index.append(f'Geração Termelétrica_{sist.Nome}')

            values[cont+2, :] = wind_scenarios[isist, icen, :]
            index.append(f'Geração Eólica_{sist.Nome}')

            values[cont+3, :] = sist.Deficit[serie_ena, :]
            index.append(f'Déficit_{sist.Nome}')

            values[cont+4, :] = sist.DemLiq[serie_ena, :]
            index.append(f'Demanda Líquida_{sist.Nome}')

            values[cont + 5, :] = sist.CMO[serie_ena, :]
            index.append(f'CMO_{sist.Nome}')

            cont += 6

        cont = 24
        for interc in simulacao.resultados[icen].Interc:
            values[cont, :] = interc.INT[serie_ena, :]
            index.append(interc.Nome)
            values[cont+1, :] = interc.INT_MAX
            index.append(f'{interc.Nome}_Máximo')

            cont += 2

        df = pd.DataFrame(data=values, index=index, columns=columns)
        df.to_excel(f'Despacho_{cenarios_eolicos[icen]}.xlsx')

    # CMO
    serie_ena = 28
    f, ax = plt.subplots(1, figsize=(20, 10))
    for icen, cen in enumerate(cenarios_eolicos):
        for isist, sist in enumerate(simulacao.resultados[icen].Sist):
            ax.plot(np.arange(1, nr_months + 1), sist.CMO[serie_ena, :], linestyle='-', color='k', lw=2, label=sist.Nome)

    plt.show()

    # Gráficos
    f, ax = plt.subplots(2, 2, figsize=(20, 10))

    serie_ena = 28
    serie_eolica = 0
    nr_estagios = simulacao.resultados[serie_eolica].nr_estagios
    pos_plots = [(0, 0), (0, 1), (1, 0), (1, 1)]
    linestyles = ['-', '-', '-', '-', '-', '-', '-']
    linewidth = 1
    alpha_color = 0.5
    colors = ['blue', 'green', 'yellow', 'red', 'gray', 'black', 'pink']
    legendas = ['Hidrelétrica', 'Termelétrica', 'Eólica', 'Déficit', 'Importação', 'Demanda Líquida', 'Excesso']
    for isist, sist in enumerate(simulacao.resultados[serie_eolica].Sist):

        total = np.zeros(nr_estagios, 'd')
        position = 0

        # Geração Hidrelétrica
        y = np.round(sist.GHidr[serie_ena, :])
        if not all(y == 0.):
            ax[pos_plots[isist][0], pos_plots[isist][1]].plot(np.arange(1, nr_estagios + 1), (total + y),
                                                              linestyle=linestyles[position], color=colors[position],
                                                              lw=linewidth, label=legendas[position])
            ax[pos_plots[isist][0], pos_plots[isist][1]].fill_between(np.arange(1, nr_estagios + 1), total, (total + y),
                                                                      facecolor=colors[position], alpha=alpha_color)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_xlabel('Estágios [meses]', fontsize=12)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_ylabel('Energia [MWmed]', fontsize=12)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_xticks(np.arange(1, nr_months + 1))
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_xlim([1, nr_months])
        total += y
        position += 1

        # Geração Termelétrica
        y = np.round(sist.GTerm[serie_ena, :])
        if not all(y == 0.):
            ax[pos_plots[isist][0], pos_plots[isist][1]].plot(np.arange(1, nr_estagios + 1), (total + y),
                                                              linestyle=linestyles[position], color=colors[position],
                                                              lw=linewidth, label=legendas[position])
            ax[pos_plots[isist][0], pos_plots[isist][1]].fill_between(np.arange(1, nr_estagios + 1), total, (total + y),
                                                                      facecolor=colors[position], alpha=alpha_color)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_xlabel('Estágio [meses]', fontsize=12)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_ylabel('Energia [MWmed]', fontsize=12)
        total += y
        position += 1

        # Geração Eólica
        y = np.round(wind_scenarios[isist, serie_eolica, :])
        if not all(y == 0.):
            ax[pos_plots[isist][0], pos_plots[isist][1]].plot(np.arange(1, nr_estagios + 1), (total + y),
                                                              linestyle=linestyles[position], color=colors[position],
                                                              lw=linewidth, label=legendas[position])
            ax[pos_plots[isist][0], pos_plots[isist][1]].fill_between(np.arange(1, nr_estagios + 1), total, (total + y),
                                                                      facecolor=colors[position], alpha=alpha_color)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_xlabel('Estágio [meses]', fontsize=12)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_ylabel('Energia [MWmed]', fontsize=12)
        total += y
        position += 1

        # Déficit
        y = np.round(sist.Deficit[serie_ena, :])
        if not all(y == 0.):
            ax[pos_plots[isist][0], pos_plots[isist][1]].plot(np.arange(1, nr_estagios + 1), (total + y),
                                                              linestyle=linestyles[position], color=colors[position],
                                                              lw=linewidth, label=legendas[position])
            ax[pos_plots[isist][0], pos_plots[isist][1]].fill_between(np.arange(1, nr_estagios + 1), total, (total + y),
                                                                      facecolor=colors[position], alpha=alpha_color)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_xlabel('Estágio [meses]', fontsize=12)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_ylabel('Energia [MWmed]', fontsize=12)
        total += y
        position += 1

        # Importação - exportação
        y = np.zeros(nr_estagios, 'd')
        # for interc in simulacao.resultados[serie_eolica].Interc:
        #     if f'->{sist.Nome}' in interc.Nome.upper():
        #         y += interc.INT[serie_ena, :]
        #     elif f'{sist.Nome}->' in interc.Nome.upper():
        #         y -= interc.INT[serie_ena, :]
        # y = np.round(y.clip(0))  # Pega apenas meses que houve importaçao: value > 0
        if not all(y == 0.):
            ax[pos_plots[isist][0], pos_plots[isist][1]].plot(np.arange(1, nr_estagios + 1), (total + y),
                                                              linestyle=linestyles[position], color=colors[position],
                                                              lw=linewidth, label=legendas[position])
            ax[pos_plots[isist][0], pos_plots[isist][1]].fill_between(np.arange(1, nr_estagios + 1), total, (total + y),
                                                                      facecolor=colors[position], alpha=alpha_color)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_xlabel('Estágio [meses]', fontsize=12)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_ylabel('Energia [MWmed]', fontsize=12)
        total += y
        position += 1

        # Demanda Líquida
        y = np.round(sist.DemLiq[serie_ena, :])
        if not all(y == 0.):
            ax[pos_plots[isist][0], pos_plots[isist][1]].plot(np.arange(1, nr_estagios + 1), y,
                                                              linestyle=linestyles[position],
                                                              color=colors[position],
                                                              lw=linewidth, label=legendas[position])
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_xlabel('Estágio [meses]', fontsize=12)
            ax[pos_plots[isist][0], pos_plots[isist][1]].set_ylabel('Energia [MWmed]', fontsize=12)

        # ax[pos_plots[isist][0], pos_plots[isist][1]].canvas.set_window_title(titulo)
        ax[pos_plots[isist][0], pos_plots[isist][1]].set_title(sist.Nome.upper(), fontsize=14)
        ax[pos_plots[isist][0], pos_plots[isist][1]].legend(fontsize=12)
        total = y
        position += 1

    plt.show()

    print('teste')

