import os
import smtplib
import psycopg2
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# Carrega as variáveis de ambiente (.env)
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://neondb_owner:npg_G5NY8gBqThCl@ep-wispy-lake-ayededeo-pooler.c-5.us-east-2.aws.neon.tech/neondb?sslmode=require")
DESTINATARIO_EMAIL = os.getenv("DESTINATARIO_EMAIL", "gabriel.cpolitano@gmail.com")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Mapeamento completo dos Cursos e Prefixo das Aulas (Total: 168 Aulas)
MAPA_CURSOS = {
    "aulas-ao-vivo": {
        "nome": "Aulas ao Vivo",
        "cor": "#e11d48", # Rose
        "prefixo": "lin-live-",
        "total": 8
    },
    "linux": {
        "nome": "Descomplicando Linux",
        "cor": "#f59e0b", # Amber/Laranja
        "prefixo": "lin-m",
        "total": 32
    },
    "terraform": {
        "nome": "Descomplicando Terraform",
        "cor": "#8b5cf6", # Roxo
        "prefixo": "tf-m",
        "total": 20
    },
    "aws": {
        "nome": "Descomplicando AWS",
        "cor": "#f97316", # Laranja
        "prefixo": "aws",
        "total": 34
    },
    "docker": {
        "nome": "Descomplicando Docker",
        "cor": "#06b6d4", # Ciano
        "prefixo": "dkr-",
        "total": 14
    },
    "golang": {
        "nome": "Golang (Exercícios & Prática)",
        "cor": "#0d9488", # Teal
        "prefixo": "go-m",
        "total": 60
    }
}

TOTAL_AULAS_GERAL = sum(c["total"] for c in MAPA_CURSOS.values()) # 168 aulas


def buscar_dados_e_gerar_relatorio():
    try:
        # Busca todas as aulas concluídas do banco Neon
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT aula_id, data_conclusao FROM curso_progresso WHERE concluida = True;"
                )
                rows = cur.fetchall()

        total_concluidas = len(rows)
        percentual_geral = round((total_concluidas / TOTAL_AULAS_GERAL) * 100, 1) if TOTAL_AULAS_GERAL > 0 else 0
        aulas_restantes = max(0, TOTAL_AULAS_GERAL - total_concluidas)

        agora_utc = datetime.now(timezone.utc)
        limite_7d = agora_utc - timedelta(days=7)
        limite_30d = agora_utc - timedelta(days=30)

        concluidas_7d = 0
        concluidas_30d = 0
        revisoes_pendentes = []

        # Estrutura para contagem por curso
        progresso_cursos = {
            cid: {"concluidas": 0, "total": cdata["total"], "nome": cdata["nome"], "cor": cdata["cor"]}
            for cid, cdata in MAPA_CURSOS.items()
        }

        for aula_id, data_str in rows:
            # 1. Identifica qual curso esta aula pertence pelo ID
            curso_identificado = False
            for cid, cinfo in MAPA_CURSOS.items():
                if aula_id.startswith(cinfo["prefixo"]):
                    progresso_cursos[cid]["concluidas"] += 1
                    curso_identificado = True
                    break

            # 2. Processa a data de conclusão para cálculos de ritmo e revisões
            if data_str:
                try:
                    prazo_custom_dias = 30
                    iso_str = data_str

                    if "|" in data_str:
                        parts = data_str.split("|")
                        iso_str = parts[0]
                        if len(parts) > 1 and parts[1].isdigit():
                            prazo_custom_dias = int(parts[1])

                    data_conclusao = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))

                    if data_conclusao >= limite_7d:
                        concluidas_7d += 1
                    if data_conclusao >= limite_30d:
                        concluidas_30d += 1

                    # Verifica se a revisão está vencida
                    dias_passados = (agora_utc - data_conclusao).days
                    if dias_passados > prazo_custom_dias:
                        revisoes_pendentes.append({
                            "aula_id": aula_id,
                            "dias_atraso": dias_passados - prazo_custom_dias,
                            "data": data_conclusao.strftime("%d/%m/%Y")
                        })
                except ValueError:
                    continue

        # --- CÁLCULOS DE EVOLUÇÃO E RITMO ---
        if concluidas_7d >= 7:
            status_ritmo, cor_status = "🔥 Ritmo Acelerado (Alta Constância)", "#16a34a"
        elif 3 <= concluidas_7d < 7:
            status_ritmo, cor_status = "🚀 Ritmo Constante (Muito Bom)", "#0284c7"
        elif 1 <= concluidas_7d < 3:
            status_ritmo, cor_status = "🐢 Ritmo Leve (Dá pra acelerar!)", "#d97706"
        else:
            status_ritmo, cor_status = "💤 Pausado (Sem evolução recente)", "#dc2626"

        if concluidas_30d > 0:
            dias_por_aula = 30 / concluidas_30d
            data_estimada = (agora_utc + timedelta(days=dias_por_aula * aulas_restantes)).strftime("%d/%m/%Y")
        else:
            data_estimada = "Indefinida (Acelere os estudos para calcular)"

        # --- GERANDO HTML DETALHADO POR CURSO ---
        html_cursos = ""
        for cid, info in progresso_cursos.items():
            qtd = info["concluidas"]
            tot = info["total"]
            pct = round((qtd / tot) * 100, 1) if tot > 0 else 0
            largura_pct = max(pct, 4)

            html_cursos += f"""
            <div style="margin-bottom: 16px; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 18px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                    <span style="font-size: 14px; font-weight: bold; color: #1e293b;">{info['nome']}</span>
                    <span style="font-size: 12px; font-weight: bold; color: #475569; font-family: monospace;">{qtd}/{tot} ({pct}%)</span>
                </div>
                <div style="background: #f1f5f9; border-radius: 10px; height: 10px; width: 100%; overflow: hidden;">
                    <div style="height: 100%; width: {largura_pct}%; background-color: {info['cor']}; border-radius: 10px;"></div>
                </div>
            </div>
            """

        # --- ALERTA DE REVISÕES PENDENTES ---
        html_revisoes = ""
        if revisoes_pendentes:
            revisoes_qtd = len(revisoes_pendentes)
            html_revisoes = f"""
            <div style="background: #fef2f2; border: 1px solid #fecaca; border-left: 4px solid #ef4444; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
                <div style="font-size: 14px; font-weight: bold; color: #991b1b; margin-bottom: 6px;">
                    ⚠️ Central de Revisões ({revisoes_qtd} aula(s) vencida(s))
                </div>
                <p style="font-size: 12px; color: #7f1d1d; margin: 0 0 10px 0;">
                    Aulas concluídas há mais de 30 dias que precisam de revisão rápida antes de entrevistas técnicas:
                </p>
                <ul style="margin: 0; padding-left: 20px; font-size: 12px; color: #991b1b;">
            """
            for rev in revisoes_pendentes[:6]: # Mostra as 6 mais urgentes
                html_revisoes += f"<li><b>Aula {rev['aula_id']}</b> (Atrasada há {rev['dias_atraso']} dias • Concluída em {rev['data']})</li>"
            
            if len(revisoes_pendentes) > 6:
                html_revisoes += f"<li>... e mais {len(revisoes_pendentes) - 6} aula(s). Acesse o painel web para ver todas.</li>"

            html_revisoes += "</ul></div>"
        else:
            html_revisoes = """
            <div style="background: #f0fdf4; border: 1px solid #bbf7d0; border-left: 4px solid #22c55e; border-radius: 8px; padding: 14px 18px; margin-bottom: 24px;">
                <span style="font-size: 13px; font-weight: bold; color: #166534;">
                    ✅ Todas as revisões técnicas estão em dia!
                </span>
            </div>
            """

# --- MONTAGEM FINAL DO E-MAIL ---
        data_formatada = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
        assunto = f"📊 [Progresso do GABRIEL] Relatório Diário - {percentual_geral}% Concluído ({total_concluidas}/{TOTAL_AULAS_GERAL})"

        corpo_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; color: #334155; }}
                .container {{ max-width: 620px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.05); }}
                .header {{ background: #0f172a; color: #ffffff; padding: 28px 24px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; tracking: -0.5px; }}
                .header p {{ margin: 6px 0 0 0; font-size: 13px; color: #38bdf8; font-weight: 500; }}
                .content {{ padding: 28px 24px; }}
                .card-main {{ background: #f1f5f9; border: 1px solid #cbd5e1; border-radius: 10px; padding: 20px; text-align: center; margin-bottom: 24px; }}
                .progress-bar-bg {{ background: #e2e8f0; border-radius: 20px; height: 18px; width: 100%; overflow: hidden; margin-top: 10px; }}
                .progress-bar-fill {{ height: 100%; border-radius: 20px; background: linear-gradient(90deg, #0284c7, #2563eb); text-align: right; line-height: 18px; font-size: 11px; color: white; font-weight: bold; padding-right: 8px; box-sizing: border-box; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 24px; }}
                .stat-box {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 14px 10px; text-align: center; }}
                .stat-value {{ font-size: 22px; font-weight: 800; margin-bottom: 2px; font-family: monospace; }}
                .stat-label {{ font-size: 10px; color: #64748b; text-transform: uppercase; font-weight: 700; }}
                .footer {{ background: #f1f5f9; padding: 18px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚀 Relatório para Matheus</h1>
                    <p>Relatório Completo de Desempenho • {data_formatada}</p>
                </div>
                
                <div class="content">
                    <!-- Progresso Geral -->
                    <div class="card-main">
                        <div style="font-size: 15px; font-weight: 800; color: #0f172a;">
                            Progresso Geral: {total_concluidas} de {TOTAL_AULAS_GERAL} Aulas Concluídas
                        </div>
                        <div class="progress-bar-bg">
                            <div class="progress-bar-fill" style="width: {max(percentual_geral, 6)}%;">{percentual_geral}%</div>
                        </div>
                    </div>

                    <!-- Métricas de Tempo -->
                    <div style="margin-bottom: 24px;">
                        <table width="100%" cellspacing="0" cellpadding="0" style="table-layout: fixed;">
                            <tr>
                                <td width="32%" class="stat-box">
                                    <div class="stat-value" style="color: #16a34a;">+{concluidas_7d}</div>
                                    <div class="stat-label">Últimos 7 dias</div>
                                </td>
                                <td width="2%"></td>
                                <td width="32%" class="stat-box">
                                    <div class="stat-value" style="color: #0284c7;">+{concluidas_30d}</div>
                                    <div class="stat-label">Últimos 30 dias</div>
                                </td>
                                <td width="2%"></td>
                                <td width="32%" class="stat-box">
                                    <div class="stat-value" style="color: #dc2626;">{aulas_restantes}</div>
                                    <div class="stat-label">Restantes</div>
                                </td>
                            </tr>
                        </table>
                    </div>

                    <!-- Revisões Pendentes -->
                    {html_revisoes}

                    <!-- Detalhamento por Curso -->
                    <div style="margin-bottom: 24px;">
                        <h3 style="font-size: 15px; font-weight: 700; color: #0f172a; margin: 0 0 14px 0; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px;">
                            📚 Desempenho Detalhado por Curso
                        </h3>
                        {html_cursos}
                    </div>

                    <!-- Análise de Ritmo -->
                    <div style="border-left: 4px solid {cor_status}; background: #f8fafc; border-top: 1px solid #e2e8f0; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; padding: 16px; border-radius: 0 8px 8px 0; margin-bottom: 32px;">
                        <div style="font-size: 13px; font-weight: bold; color: #0f172a; margin-bottom: 6px;">
                            📊 Análise de Evolução & Previsão
                        </div>
                        <p style="font-size: 13px; color: #334155; margin: 0 0 4px 0;">
                            <strong>Ritmo Atual:</strong> <span style="color: {cor_status}; font-weight: bold;">{status_ritmo}</span>
                        </p>
                        <p style="font-size: 13px; color: #334155; margin: 0;">
                            <strong>Estimativa para Término Total:</strong> {data_estimada}
                        </p>
                    </div>
                    
                    <!-- Botão para Relatório Completo Web -->
                    <div style="text-align: center; margin-bottom: 10px;">
                        <a href="https://tracker-class.vercel.app/?view=relatorio" target="_blank" style="background-color: #0284c7; color: #ffffff; text-decoration: none; padding: 14px 28px; border-radius: 8px; font-weight: bold; font-size: 14px; display: inline-block;">
                            Ver Relatório Completo na Web
                        </a>
                    </div>
                </div>

                <div class="footer">
                    🎯 <b>Acompanhamento Completo e Diário do GABRIEL</b>
                </div>
            </div>
        </body>
        </html>
        """
        return assunto, corpo_html

    except Exception as e:
        print(f"❌ Erro ao conectar ao banco Neon ou gerar relatório: {e}", flush=True)
        return None, None


def enviar_email():
    print(f"⏰ [{datetime.now().strftime('%H:%M:%S')}] Gerando relatório de estudos DevOps...", flush=True)
    assunto, corpo_html = buscar_dados_e_gerar_relatorio()

    if not assunto or not corpo_html:
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = DESTINATARIO_EMAIL
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo_html, 'html', 'utf-8'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, DESTINATARIO_EMAIL, msg.as_string())

        print(f"✅ Relatório detalhado enviado com sucesso para {DESTINATARIO_EMAIL}!", flush=True)
    except Exception as e:
        print(f"❌ Erro ao enviar e-mail via SMTP: {e}", flush=True)


if __name__ == "__main__":
    print("🚀 Servidor de Relatório DevOps iniciado com sucesso!", flush=True)

    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")

    # Executa todos os dias às 12:00 PM (Horário de Brasília)
    scheduler.add_job(
        enviar_email,
        CronTrigger(hour=12, minute=0, timezone="America/Sao_Paulo")
    )

    # Se desejar testar um envio imediato ao iniciar o script, remova o '#' abaixo:
    # enviar_email()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 Servidor encerrado.", flush=True)