import streamlit as st
import fitz  # PyMuPDF
from PIL import Image, ImageEnhance
import io
import os
import re
from streamlit_drawable_canvas import st_canvas
import easyocr
import numpy as np
import pandas as pd
from datetime import datetime

# ==========================================
# CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(layout="wide", page_title="Planta Interativa do Loteamento - HABITE", page_icon="🏗️")

if "canvas_key" not in st.session_state:
    st.session_state["canvas_key"] = 0

def limpar_selecao():
    st.session_state["canvas_key"] += 1

# ==========================================
# CSS PERSONALIZADO
# ==========================================
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; font-family: 'Inter', sans-serif; }
    #MainMenu, footer, header {visibility: hidden;}
    .main-title { font-size: 2rem; font-weight: 700; color: #1e293b; margin-bottom: 0.2rem; }
    .sub-title { font-size: 0.95rem; color: #64748b; margin-bottom: 1rem; }
    .card-header { font-size: 1.25rem; font-weight: 600; color: #0f172a; margin-bottom: 16px; border-bottom: 2px solid #f1f5f9; padding-bottom: 10px; }
    div[data-baseweb="input"] { border-radius: 8px !important; border-color: #cbd5e1 !important; background-color: #f8fafc !important; }
    .stTextInput label { font-size: 0.85rem !important; font-weight: 600 !important; color: #475569 !important; text-transform: uppercase; }
    .stButton>button { width: 100%; border-radius: 8px !important; font-weight: 600 !important; padding: 0.5rem 1rem !important; }
    div[data-testid="stButton"] button[kind="secondary"] { background-color: #ffffff !important; color: #475569 !important; border: 1px solid #cbd5e1 !important; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2563eb !important; color: white !important; border: none !important; }
    </style>
""", unsafe_allow_html=True)

pdf_path = r"C:\assinatura\LOTES\PLANTA SETEMBRO 2026 ABAIS.pdf"

@st.cache_resource
def carregar_ocr():
    return easyocr.Reader(['pt', 'en'])

reader = carregar_ocr()

@st.cache_data
def carregar_imagem_pdf(caminho_pdf):
    if not os.path.exists(caminho_pdf):
        st.error(f"Arquivo não encontrado: {caminho_pdf}")
        st.stop()
    doc = fitz.open(caminho_pdf)
    page = doc.load_page(0)
    pix = page.get_pixmap(dpi=200)
    return Image.open(io.BytesIO(pix.tobytes("png")))

img = carregar_imagem_pdf(pdf_path)

# ==========================================
# ESTRUTURA DO CABEÇALHO
# ==========================================
col_titulo, col_painel_topo = st.columns([3, 2], gap="large")

with col_titulo:
    col_logo, col_header_txt = st.columns([1, 3])
    with col_logo:
        if os.path.exists("habite.jpg"):
            st.image("habite.jpg", use_container_width=True)
        elif os.path.exists("habite.png"):
            st.image("habite.png", use_container_width=True)
        else:
            st.warning("⚠️ Logo não encontrada.")

    with col_header_txt:
        st.markdown('<div class="main-title">Planta Interativa do Loteamento</div>', unsafe_allow_html=True)
        st.markdown('<div class="sub-title">Sistema de Consulta e Mapeamento Cadastral de Lotes</div>', unsafe_allow_html=True)
    
    st.info("💡 **Instruções:** Desenhe um retângulo sobre o lote na planta para extrair ou consultar os dados armazenados.")

largura_canvas = int(img.width * 0.6)
altura_canvas = int(img.height * 0.6)

escala_x = img.width / largura_canvas
escala_y = img.height / altura_canvas

def executar_ocr_hibrido(imagem_pil):
    enhancer = ImageEnhance.Contrast(imagem_pil)
    img_proc = enhancer.enhance(1.8)
    
    res_h = reader.readtext(np.array(img_proc), detail=0)
    img_rot = img_proc.rotate(90, expand=True)
    res_v = reader.readtext(np.array(img_rot), detail=0)
    
    todos = res_h + res_v
    unicos = []
    for item in todos:
        if item not in unicos:
            unicos.append(item)
    return unicos

def extrair_dados_puros(textos, textos_entorno):
    num_lote, inscricao, matricula, quadra = "", "", "", ""
    proprietario, medidas_encontradas = [], []

    todos_textos = textos + textos_entorno
    
    # 1. Identificação da Quadra (ex: QD)
    for item in todos_textos:
        txt = str(item).strip().upper()
        if not quadra:
            match_q = re.search(r'\bQ[A-Z]\b', txt) or re.search(r'\bQUADRA\s?[A-Z]\b', txt)
            if match_q:
                quadra = match_q.group(0).replace("QUADRA", "").strip()
                if len(quadra) == 1:
                    quadra = f"Q{quadra}"

    # 2. Extração de Dimensões
    for item in todos_textos:
        txt = str(item).strip().upper().replace(',', '.')
        match_dim = re.search(r'\b\d{2}\.\d{2,3}\b', txt)
        if match_dim:
            try:
                medidas_encontradas.append(round(float(match_dim.group(0)), 2))
            except ValueError:
                pass

    # 3. Extração Direcionada dos Dados Principais
    candidatos_lote = []
    
    for item in textos:
        txt = str(item).strip().upper()

        # Matrícula (exatamente 5 dígitos no topo do círculo, ex: 21772)
        if len(txt) == 5 and txt.isdigit() and not matricula:
            matricula = txt
            continue

        # Inscrição Municipal (exatamente 4 dígitos na base do círculo, ex: 1306)
        if len(txt) == 4 and txt.isdigit() and not inscricao:
            inscricao = txt
            continue

        # Número do lote (1 ou 2 dígitos, ex: 01)
        if len(txt) in [1, 2] and txt.isdigit():
            candidatos_lote.append(txt)
            continue

        # Texto para proprietário/situação
        if len(txt) > 2 and not txt.isdigit() and not txt.startswith("Q"):
            if not re.search(r'\d{2}\.\d{2,3}', txt):
                proprietario.append(txt)

    if candidatos_lote:
        # Pega o último número identificado (posição inferior do lote)
        num_lote = str(int(candidatos_lote[-1])).zfill(2)

    # Cálculo das Dimensões
    larguras = [m for m in medidas_encontradas if m < 27.0]
    comprimentos = [m for m in medidas_encontradas if m >= 27.0]

    frente = larguras[0] if len(larguras) > 0 else 24.00
    fundo = larguras[1] if len(larguras) > 1 else frente

    if len(comprimentos) >= 2:
        lado_1, lado_2 = min(comprimentos), max(comprimentos)
    elif len(comprimentos) == 1:
        lado_1, lado_2 = comprimentos[0], comprimentos[0]
    else:
        lado_1, lado_2 = 29.00, 29.00

    media_largura = (frente + fundo) / 2.0
    media_comprimento = (lado_1 + lado_2) / 2.0
    area_m2 = media_largura * media_comprimento

    str_largura = f"{frente:.2f}m" if frente == fundo else f"({frente:.2f}m + {fundo:.2f}m)/2"
    str_comprimento = f"{lado_1:.2f}m" if lado_1 == lado_2 else f"({lado_1:.2f}m + {lado_2:.2f}m)/2"

    dim_str = f"{str_largura} x {str_comprimento}"
    area_str = f"{area_m2:.2f} m²"
    prop_str = " / ".join(proprietario) if proprietario else "HABITE / PREFEITURA"

    return quadra, num_lote, inscricao, matricula, dim_str, area_str, prop_str

# Busca por Coordenadas Normalizadas no CSV
def buscar_lote_por_coordenadas_normalizadas(norm_x, norm_y, norm_w, norm_h, arquivo_csv):
    if not os.path.exists(arquivo_csv):
        return None
    
    try:
        df = pd.read_csv(arquivo_csv, sep=';', dtype=str)
        if "Norm_X" not in df.columns:
            return None

        centro_x = norm_x + (norm_w / 2.0)
        centro_y = norm_y + (norm_h / 2.0)
        
        for idx, row in df.iterrows():
            try:
                rx = float(str(row["Norm_X"]).replace(',', '.'))
                ry = float(str(row["Norm_Y"]).replace(',', '.'))
                rw = float(str(row["Norm_W"]).replace(',', '.'))
                rh = float(str(row["Norm_H"]).replace(',', '.'))
                
                # Checa se o centroide cai dentro da bounding box cadastrada
                if (rx <= centro_x <= rx + rw) and (ry <= centro_y <= ry + rh):
                    return row.to_dict()
            except (ValueError, TypeError):
                continue

        return None
    except Exception:
        return None

with col_painel_topo:
    st.markdown('<div class="card-header">📋 Ficha Técnica do Lote</div>', unsafe_allow_html=True)
    placeholder_form = st.empty()

canvas_result = st_canvas(
    fill_color="rgba(37, 99, 235, 0.2)",
    stroke_color="#2563eb",
    stroke_width=2,
    background_image=img,
    update_streamlit=True,
    height=altura_canvas,
    width=largura_canvas,
    drawing_mode="rect",
    key=f"canvas_lotes_{st.session_state['canvas_key']}",
)

if canvas_result.json_data is not None and len(canvas_result.json_data["objects"]) > 0:
    ultimo_lote = canvas_result.json_data["objects"][-1]
    
    x = float(ultimo_lote["left"])
    y = float(ultimo_lote["top"])
    w = float(ultimo_lote["width"])
    h = float(ultimo_lote["height"])

    # Normalização relativa ao canvas (0.0 a 1.0)
    norm_x = round(x / largura_canvas, 4)
    norm_y = round(y / altura_canvas, 4)
    norm_w = round(w / largura_canvas, 4)
    norm_h = round(h / altura_canvas, 4)

    arquivo_csv = "lotes_salvos.csv"
    
    # 1. Consulta no Banco de Dados por Coordenadas Normalizadas
    lote_encontrado = buscar_lote_por_coordenadas_normalizadas(norm_x, norm_y, norm_w, norm_h, arquivo_csv)

    if lote_encontrado:
        q = str(lote_encontrado.get("Quadra", "") or "")
        lote = str(lote_encontrado.get("Lote", "") or "")
        insc = str(lote_encontrado.get("Inscrição Municipal", "") or "")
        mat = str(lote_encontrado.get("Matrícula", "") or "")
        dim = str(lote_encontrado.get("Dimensões", "") or "")
        area = str(lote_encontrado.get("Área Total", "") or "")
        prop = str(lote_encontrado.get("Proprietário/Situação", "") or "")
        mensagem_status = f"🎯 **Lote {lote} (Quadra {q}) carregado do Banco de Dados com sucesso!**"
    else:
        # 2. Executa OCR apenas se for um lote novo
        crop_x1 = max(0, int(x * escala_x))
        crop_y1 = max(0, int(y * escala_y))
        crop_x2 = min(img.width, int((x + w) * escala_x))
        crop_y2 = min(img.height, int((y + h) * escala_y))

        margem = 100
        env_x1 = max(0, crop_x1 - margem)
        env_y1 = max(0, crop_y1 - margem)
        env_x2 = min(img.width, crop_x2 + margem)
        env_y2 = min(img.height, crop_y2 + margem)

        imagem_recortada = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))
        imagem_entorno = img.crop((env_x1, env_y1, env_x2, env_y2))

        resultados_ocr = executar_ocr_hibrido(imagem_recortada)
        resultados_entorno = executar_ocr_hibrido(imagem_entorno)

        q, lote, insc, mat, dim, area, prop = extrair_dados_puros(resultados_ocr, resultados_entorno)
        mensagem_status = "✨ Novo lote detectado via OCR com sucesso!"

    with placeholder_form.container():
        st.success(mensagem_status)
        st.button("🔄 Limpar Seleção / Nova Consulta", type="secondary", on_click=limpar_selecao, use_container_width=True)
        
        with st.form(key="form_lote_topo_v26"):
            col_f1, col_f2 = st.columns(2)
            with col_f1:
                v_quadra = st.text_input("Quadra", value=q)
                v_lote = st.text_input("Número do Lote", value=lote)
                v_inscricao = st.text_input("Inscrição Municipal", value=insc)
                v_matricula = st.text_input("Matrícula", value=mat)
            with col_f2:
                v_dimensoes = st.text_input("Dimensões do Lote", value=dim)
                v_area = st.text_input("Área Total", value=area)
                v_proprietario = st.text_input("Situação / Proprietário", value=prop)
            
            salvar = st.form_submit_button("Confirmar e Salvar Registro", type="primary", use_container_width=True)

            if salvar:
                q_fmt = v_quadra.strip().upper()
                lote_fmt = v_lote.strip().zfill(2) if v_lote.strip().isdigit() else v_lote.strip().upper()
                
                novo_registro = {
                    "Data/Hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "Quadra": q_fmt,
                    "Lote": lote_fmt,
                    "Inscrição Municipal": v_inscricao.strip(),
                    "Matrícula": v_matricula.strip(),
                    "Dimensões": v_dimensoes.strip(),
                    "Área Total": v_area.strip(),
                    "Proprietário/Situação": v_proprietario.strip(),
                    "Norm_X": norm_x,
                    "Norm_Y": norm_y,
                    "Norm_W": norm_w,
                    "Norm_H": norm_h
                }

                if os.path.exists(arquivo_csv):
                    df_existente = pd.read_csv(arquivo_csv, sep=';', dtype=str)
                    
                    if "Quadra" in df_existente.columns and "Lote" in df_existente.columns:
                        df_existente["Quadra"] = df_existente["Quadra"].astype(str).str.strip().str.upper()
                        df_existente["Lote"] = df_existente["Lote"].astype(str).str.strip().str.upper()

                        idx_duplicado = df_existente[
                            (df_existente["Quadra"] == q_fmt) & 
                            (df_existente["Lote"] == lote_fmt)
                        ].index

                        if not idx_duplicado.empty:
                            for key, val in novo_registro.items():
                                df_existente.loc[idx_duplicado, key] = str(val)
                            df_existente.to_csv(arquivo_csv, sep=';', index=False, encoding='utf-8-sig')
                            st.warning(f"⚠️ Lote {lote_fmt} (Quadra {q_fmt}) atualizado com novas coordenadas!")
                        else:
                            df_novo = pd.DataFrame([novo_registro])
                            df_novo.to_csv(arquivo_csv, sep=';', mode='a', header=False, index=False, encoding='utf-8-sig')
                            st.success(f"✅ Lote {lote_fmt} (Quadra {q_fmt}) salvo no banco!")
                    else:
                        df_novo = pd.DataFrame([novo_registro])
                        df_novo.to_csv(arquivo_csv, sep=';', mode='w', header=True, index=False, encoding='utf-8-sig')
                        st.success(f"✅ Arquivo atualizado e Lote {lote_fmt} salvo!")
                else:
                    df_novo = pd.DataFrame([novo_registro])
                    df_novo.to_csv(arquivo_csv, sep=';', mode='w', header=True, index=False, encoding='utf-8-sig')
                    st.success(f"✅ Lote {lote_fmt} salvo no banco!")

else:
    with placeholder_form.container():
        st.info("Aguardando seleção na planta...")

# ==========================================
# PAINEL DE LOTES MAPEADOS
# ==========================================
st.markdown("---")
st.markdown('<div class="card-header">📊 Lotes Mapeados no Sistema</div>', unsafe_allow_html=True)

arquivo_csv = "lotes_salvos.csv"
if os.path.exists(arquivo_csv):
    try:
        df_lotes = pd.read_csv(arquivo_csv, sep=';', dtype=str)
        colunas_exibicao = [c for c in df_lotes.columns if not c.startswith("Norm_") and not c.startswith("Coord_")]
        st.dataframe(df_lotes[colunas_exibicao], use_container_width=True, hide_index=True)
    except Exception:
        st.error("Erro ao ler a tabela de lotes salvos.")
else:
    st.write("Nenhum lote salvo até o momento.")
