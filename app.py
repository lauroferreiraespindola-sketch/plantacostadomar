import streamlit as st
import cv2
import numpy as np
import pandas as pd
import easyocr
import re
import os
from PIL import Image
from streamlit_drawable_canvas import st_canvas
import fitz  # PyMuPDF

# ==========================================
# CONFIGURAÇÃO DA PÁGINA (RESPONSIVA / MOBILE)
# ==========================================
st.set_page_config(
    page_title="HABITE - Leitor de Plantas",
    page_icon="📐",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilo CSS customizado para adaptar a tela a telemóveis/celulares
st.markdown("""
    <style>
        .main .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            padding-left: 0.5rem;
            padding-right: 0.5rem;
        }
        .stButton>button {
            width: 100%;
            border-radius: 8px;
            height: 3em;
            background-color: #FF4B4B;
            color: white;
            font-weight: bold;
        }
        .stTextInput>div>div>input {
            border-radius: 6px;
        }
    </style>
""", unsafe_allow_html=True)

CSV_FILE = "lotes_salvos.csv"
PDF_FILE_NAME = "PLANTA SETEMBRO 2026 ABAIS.pdf"

# ==========================================
# FUNÇÕES DE BANCO DE DADOS E CONVERÇÃO PDF
# ==========================================
@st.cache_resource
def load_ocr_reader():
    return easyocr.Reader(['pt', 'en'], gpu=False)

reader = load_ocr_reader()

def carregar_ou_converter_pdf(pdf_path):
    """Carrega o PDF do repositório e converte a 1ª página para PIL Image."""
    if os.path.exists(pdf_path):
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        return img
    return None

def carregar_dados_csv():
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE, sep=';', dtype=str)
        cols_float = ['Norm_X', 'Norm_Y', 'Norm_W', 'Norm_H']
        for c in cols_float:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
        return df
    else:
        return pd.DataFrame(columns=[
            'Quadra', 'Lote', 'Inscricao_Municipal', 'Matricula',
            'Dimensoes', 'Area_m2', 'Situacao_Proprietario',
            'Norm_X', 'Norm_Y', 'Norm_W', 'Norm_H'
        ])

def salvar_registro_csv(dados):
    df = carregar_dados_csv()
    
    # Remove duplicados por Quadra + Lote antes de salvar
    df = df[~((df['Quadra'] == dados['Quadra']) & (df['Lote'] == dados['Lote']))]
    
    novo_df = pd.DataFrame([dados])
    df_final = pd.concat([df, novo_df], ignore_index=True)
    df_final.to_csv(CSV_FILE, sep=';', index=False)

def buscar_lote_por_iou(norm_x, norm_y, norm_w, norm_h, df, limiar_iou=0.3):
    """Verifica se a área desenhada no celular corresponde a um lote já salvo."""
    if df.empty or 'Norm_X' not in df.columns:
        return None

    box_a = [norm_x, norm_y, norm_x + norm_w, norm_y + norm_h]
    melhor_match = None
    maior_iou = 0.0

    for idx, row in df.iterrows():
        try:
            rx, ry, rw, rh = float(row['Norm_X']), float(row['Norm_Y']), float(row['Norm_W']), float(row['Norm_H'])
            if rw == 0 or rh == 0:
                continue
            
            box_b = [rx, ry, rx + rw, ry + rh]

            xA = max(box_a[0], box_b[0])
            yA = max(box_a[1], box_b[1])
            xB = min(box_a[2], box_b[2])
            yB = min(box_a[3], box_b[3])

            interArea = max(0, xB - xA) * max(0, yB - yA)
            boxAArea = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
            boxBArea = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])

            iou = interArea / float(boxAArea + boxBArea - interArea)

            if iou > maior_iou and iou >= limiar_iou:
                maior_iou = iou
                melhor_match = row.to_dict()
        except:
            continue

    return melhor_match

# ==========================================
# EXTRAÇÃO OCR REFINADA
# ==========================================
def extrair_dados_puros(textos, textos_entorno):
    num_lote, inscricao, matricula, quadra = "", "", "", ""
    proprietario, medidas_encontradas = [], []

    todos_textos = textos + textos_entorno

    # Quadra
    for item in todos_textos:
        txt = str(item).strip().upper()
        if not quadra:
            match_q = re.search(r'\bQ[A-Z]\b', txt) or re.search(r'\bQUADRA\s?[A-Z]\b', txt)
            if match_q:
                quadra = match_q.group(0).replace("QUADRA", "").strip()
                if len(quadra) == 1:
                    quadra = f"Q{quadra}"

    # Dimensões
    for item in todos_textos:
        txt = str(item).strip().upper().replace(',', '.')
        match_dim = re.search(r'\b\d{2}\.\d{2,3}\b', txt)
        if match_dim:
            try:
                medidas_encontradas.append(round(float(match_dim.group(0)), 2))
            except ValueError:
                pass

    candidatos_numeros = []

    for item in textos:
        txt = str(item).strip().upper()

        # Matrícula (exatamente 5 dígitos, ex: 21772)
        if len(txt) == 5 and txt.isdigit() and not matricula:
            matricula = txt
            continue

        # Inscrição Municipal (exatamente 4 dígitos, ex: 1306)
        if len(txt) == 4 and txt.isdigit() and not inscricao:
            inscricao = txt
            continue

        # Candidatos a Número do Lote (1 ou 2 dígitos)
        if (len(txt) in [1, 2]) and txt.isdigit():
            candidatos_numeros.append(txt)
            continue

        if len(txt) > 2 and not txt.isdigit() and not txt.startswith("Q"):
            if not re.search(r'\d{2}\.\d{2,3}', txt):
                proprietario.append(txt)

    if candidatos_numeros:
        num_lote = str(int(candidatos_numeros[-1])).zfill(2)

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

# ==========================================
# INTERFACE PRINCIPAL
# ==========================================
st.title("📐 HABITE EMPREENDIMENTOS")
st.caption("Acesse e cadastre lotes diretamente pelo celular")

# Carrega Imagem da Planta
img_planta = carregar_ou_converter_pdf(PDF_FILE_NAME)

if img_planta is None:
    st.error(f"Arquivo '{PDF_FILE_NAME}' não foi encontrado no repositório.")
else:
    orig_w, orig_h = img_planta.size
    
    # Responsividade no celular (largura máxima ajustável)
    canvas_width = min(800, orig_w)
    scale_factor = canvas_width / float(orig_w)
    canvas_height = int(orig_h * scale_factor)

    st.info("💡 **Instruções:** Arraste o dedo ou o cursor sobre o lote para consultar ou registrar os dados.")

    col1, col2 = st.columns([1.2, 1])

    with col1:
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)",
            stroke_width=2,
            stroke_color="#FF0000",
            background_image=img_planta,
            update_streamlit=True,
            height=canvas_height,
            width=canvas_width,
            drawing_mode="rect",
            key="canvas_loteamento",
        )

    # Processamento da área selecionada
    if canvas_result.json_data is not None:
        objects = canvas_result.json_data["objects"]
        if len(objects) > 0:
            last_rect = objects[-1]
            left, top = last_rect["left"], last_rect["top"]
            w, h = last_rect["width"], last_rect["height"]

            if w > 5 and h > 5:
                # Normalização das Coordenadas (0.0 a 1.0)
                norm_x = left / float(canvas_width)
                norm_y = top / float(canvas_height)
                norm_w = w / float(canvas_width)
                norm_h = h / float(canvas_height)

                df_banco = carregar_dados_csv()
                registro_existente = buscar_lote_por_iou(norm_x, norm_y, norm_w, norm_h, df_banco)

                if registro_existente:
                    st.success(f"🎯 Lote {registro_existente['Lote']} (Quadra {registro_existente['Quadra']}) carregado do Banco de Dados!")
                    q_val = registro_existente['Quadra']
                    l_val = registro_existente['Lote']
                    i_val = registro_existente['Inscricao_Municipal']
                    m_val = registro_existente['Matricula']
                    d_val = registro_existente['Dimensoes']
                    a_val = registro_existente['Area_m2']
                    p_val = registro_existente['Situacao_Proprietario']
                else:
                    # Executa OCR se o lote ainda não estiver salvo
                    crop_left = int(left / scale_factor)
                    crop_top = int(top / scale_factor)
                    crop_w = int(w / scale_factor)
                    crop_h = int(h / scale_factor)

                    crop_img = img_planta.crop((crop_left, crop_top, crop_left + crop_w, crop_top + crop_h))
                    cv_crop = cv2.cvtColor(np.array(crop_img), cv2.COLOR_RGB2BGR)

                    ocr_0 = reader.readtext(cv_crop, detail=0)
                    cv_crop_90 = cv2.rotate(cv_crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
                    ocr_90 = reader.readtext(cv_crop_90, detail=0)

                    q_val, l_val, i_val, m_val, d_val, a_val, p_val = extrair_dados_puros(ocr_0, ocr_90)
                    st.toast("✨ Novo lote detectado via OCR com sucesso!")

                # Exibição e Edição nos Formulários do Mobile
                with col2:
                    with st.form("form_lote"):
                        q_input = st.text_input("QUADRA", value=q_val)
                        l_input = st.text_input("NÚMERO DO LOTE", value=l_val)
                        i_input = st.text_input("INSCRIÇÃO MUNICIPAL", value=i_val)
                        m_input = st.text_input("MATRÍCULA", value=m_val)
                        d_input = st.text_input("DIMENSÕES DO LOTE", value=d_val)
                        a_input = st.text_input("ÁREA TOTAL", value=a_val)
                        p_input = st.text_input("SITUAÇÃO / PROPRIETÁRIO", value=p_val)

                        if st.form_submit_button("Confirmar e Salvar Registro"):
                            dados_salvar = {
                                'Quadra': q_input,
                                'Lote': l_input,
                                'Inscricao_Municipal': i_input,
                                'Matricula': m_input,
                                'Dimensoes': d_input,
                                'Area_m2': a_input,
                                'Situacao_Proprietario': p_input,
                                'Norm_X': norm_x,
                                'Norm_Y': norm_y,
                                'Norm_W': norm_w,
                                'Norm_H': norm_h
                            }
                            salvar_registro_csv(dados_salvar)
                            st.success(f"✅ Registro do Lote {l_input} salvo com sucesso!")
