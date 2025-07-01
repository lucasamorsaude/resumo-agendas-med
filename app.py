import os
import requests
import pandas as pd
from datetime import date, timedelta

from login_auth import get_auth_new

# --- 1. CONFIGURAÇÃO E FUNÇÕES ---

auth = get_auth_new()
# Pega as credenciais e o webhook do Slack dos Secrets do GitHub
AUTH_TOKEN = auth
COOKIE = os.environ.get('API_COOKIE')

SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_CHANNEL_ID = os.environ.get('SLACK_CHANNEL_ID') 

# Headers para a API
HEADERS = {
    'Authorization': f"Bearer {AUTH_TOKEN}",
    'Cookie': COOKIE
}

# URLs das APIs
PROFISSIONAIS_URL = 'https://amei.amorsaude.com.br/api/v1/profissionais/by-unidade'
SLOTS_URL = 'https://amei.amorsaude.com.br/api/v1/slots/list-slots-by-professional'

def get_all_professionals():
    """Busca todos os profissionais da unidade."""
    try:
        response = requests.get(PROFISSIONAIS_URL, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar profissionais: {e}")
        return None

def get_slots_for_professional(professional_id, target_date):
    """Busca os agendamentos de um profissional para uma data específica."""
    params = {
        'idClinic': 932,
        'idSpecialty': 'null',
        'idProfessional': professional_id,
        'initialDate': target_date.strftime('%Y%m%d'),
        'finalDate': target_date.strftime('%Y%m%d'),
        'initialHour': '00:00',
        'endHour': '23:59'
    }
    try:
        response = requests.get(SLOTS_URL, headers=HEADERS, params=params)
        response.raise_for_status()
        data = response.json()
        if data and isinstance(data, list) and len(data) > 0:
            return data[0].get('hours', [])
        return []
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar slots para o profissional {professional_id}: {e}")
        return []

def format_slack_message(summary_df):
    """Formata o DataFrame de resumo para uma mensagem de Slack."""
    # Pega a data de amanhã para o título
    tomorrow = date.today() + timedelta(days=1)
    message = f"📅 *Resumo da Agenda - {tomorrow.strftime('%d/%m/%Y')}*\n\n"

    # Filtra apenas os profissionais que têm agendamentos
    summary_df = summary_df[summary_df['Total Agendado'] > 0]

    if summary_df.empty:
        message += "Nenhum paciente agendado para amanhã."
        return message

    # Formata a tabela de resumo
    message += "```\n"
    message += summary_df.to_string(columns=['Total Agendado'])
    message += "\n```"
    return message

def send_to_slack(message):
    """Envia a mensagem para um canal do Slack usando um token de bot."""
    if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
        print("Token de Bot ou ID do Canal do Slack não configurados.")
        return

    api_url = 'https://slack.com/api/chat.postMessage'
    headers = {
        'Authorization': f'Bearer {SLACK_BOT_TOKEN}',
        'Content-Type': 'application/json; charset=utf-8'
    }
    payload = {
        'channel': SLACK_CHANNEL_ID,
        'text': message
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        response_data = response.json()
        if response_data.get("ok"):
            print("Resumo enviado para o Slack com sucesso!")
        else:
            print(f"Erro retornado pela API do Slack: {response_data.get('error')}")
    except requests.exceptions.RequestException as e:
        print(f"Erro de conexão ao enviar para o Slack: {e}")

# --- 2. EXECUÇÃO PRINCIPAL ---

if __name__ == "__main__":
    target_date = date.today() + timedelta(days=1)
    profissionais = get_all_professionals()
    
    if profissionais:
        resumo_geral = {}
        
        for prof in profissionais:
            prof_id = prof.get('id')
            prof_nome = prof.get('nome', f'ID {prof_id}')
            
            slots = get_slots_for_professional(prof_id, target_date)
            
            contagem_status = {}
            for slot in slots:
                status_atual = slot.get('status', 'Indefinido')
                contagem_status[status_atual] = contagem_status.get(status_atual, 0) + 1
            
            if contagem_status:
                resumo_geral[prof_nome] = contagem_status

        if resumo_geral:
            df_resumo = pd.DataFrame.from_dict(resumo_geral, orient='index').fillna(0)
            
            # Soma apenas os status que contam como agendamento
            status_agendamento = [
                "Marcado - confirmado", "Em atendimento", "Agendado", "Encaixe", 
                "Aguardando atendimento", "Aguardando pós-consulta"
            ]
            
            # Garante que as colunas existam no DataFrame antes de somar
            colunas_para_somar = [s for s in status_agendamento if s in df_resumo.columns]
            df_resumo['Total Agendado'] = df_resumo[colunas_para_somar].sum(axis=1).astype(int)

            # Ordena pelo profissional com mais agendamentos
            df_resumo = df_resumo.sort_values(by='Total Agendado', ascending=False)
            
            # Formata e envia a mensagem
            slack_message = format_slack_message(df_resumo)
            send_to_slack(slack_message)
        else:
            print(f"Nenhum agendamento encontrado para {target_date.strftime('%d/%m/%Y')}.")
    else:
        print("Não foi possível obter a lista de profissionais.")