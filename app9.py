import streamlit as st
from streamlit_ace import st_ace
import sys
from io import StringIO
from supabase import create_client, Client
import ast
import pprint

# --- Configuration de la page ---
st.set_page_config(page_title="pyAPEX", layout="wide")

# --- CONNEXION SUPABASE ---
# On utilise st.cache_resource pour ne se connecter qu'une seule fois
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# MOT DE PASSE PROFESSEUR (Depuis les secrets aussi)
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]

# ==============================================================================
# 1. GESTION DES DONNÉES (Remplacement JSON par SUPABASE)
# ==============================================================================

def load_exercices():
    """Récupère tous les exercices depuis Supabase, triés par ID"""
    try:
        response = supabase.table("exercises").select("*").order("id").execute()
        return response.data # Retourne une liste de dictionnaires
    except Exception as e:
        st.error(f"Erreur de connexion DB : {e}")
        return []

def add_exercice(exo_data):
    """Ajoute un exercice dans Supabase"""
    try:
        supabase.table("exercises").insert(exo_data).execute()
        return True
    except Exception as e:
        st.error(f"Erreur ajout : {e}")
        return False

def update_exercice(exo_id, exo_data):
    """Met à jour un exercice existant"""
    try:
        supabase.table("exercises").update(exo_data).eq("id", exo_id).execute()
        return True
    except Exception as e:
        st.error(f"Erreur modification : {e}")
        return False

def delete_exercice(exo_id):
    """Supprime un exercice"""
    try:
        supabase.table("exercises").delete().eq("id", exo_id).execute()
        return True
    except Exception as e:
        st.error(f"Erreur suppression : {e}")
        return False

def init_session_state():
    if 'sauvegarde_codes' not in st.session_state:
        st.session_state['sauvegarde_codes'] = {} 
    if 'sauvegarde_tests' not in st.session_state:
        st.session_state['sauvegarde_tests'] = {} 
    if 'console_output' not in st.session_state:
        st.session_state['console_output'] = {}
    if 'validation_result' not in st.session_state:
        st.session_state['validation_result'] = {}
    if 'completed_exercises' not in st.session_state:
        st.session_state['completed_exercises'] = set()

# ==============================================================================
# 2. FONCTION D'AFFICHAGE (Peu de changements ici)
# ==============================================================================
def afficher_exercice(exercice):
    # NOTE : Avec Supabase, l'ID est unique, on peut s'en servir comme clé si besoin
    # Mais ici on garde le titre comme clé pour l'interface
    titre_actuel = exercice['titre']
    
    if titre_actuel not in st.session_state['console_output']:
        st.session_state['console_output'][titre_actuel] = ""
    if titre_actuel not in st.session_state['validation_result']:
        st.session_state['validation_result'][titre_actuel] = None

    # Init Code
    if titre_actuel not in st.session_state['sauvegarde_codes']:
        # Supabase retourne 'args' comme une liste directe (grâce au type JSONB), pas besoin de parsing complexe
        args_clean = exercice['args'] 
        args_str = ", ".join(args_clean)
        template = f"def {exercice['nom_fonction']}({args_str}):\n    # votre code ici \n    return 0"
        st.session_state['sauvegarde_codes'][titre_actuel] = template
    
    valeur_code = st.session_state['sauvegarde_codes'][titre_actuel]

    if titre_actuel not in st.session_state['sauvegarde_tests']:
        st.session_state['sauvegarde_tests'][titre_actuel] = exercice['tests_par_defaut']
    
    valeur_tests = st.session_state['sauvegarde_tests'][titre_actuel]

    # Layout
    row1_col1, row1_col2 = st.columns([1, 1])
    with row1_col1:
        st.subheader("📋 Énoncé")
        st.info(exercice['description'])
        st.caption(f"Fonction : `{exercice['nom_fonction']}`")

    with row1_col2:
        st.subheader("Votre Code")
        code_etudiant = st_ace(
            value=valeur_code,
            language='python',
            theme='monokai',
            key=f"ace_code_{titre_actuel}",
            height=300,
            auto_update=True
        )
        st.session_state['sauvegarde_codes'][titre_actuel] = code_etudiant

    st.markdown("---")

    row2_col1, row2_col2 = st.columns([1, 1])
    with row2_col2:
        st.subheader("Vos données de test")
        code_tests = st_ace(
            value=valeur_tests,
            language='python',
            theme='monokai',
            key=f"ace_tests_{titre_actuel}",
            height=200,
            auto_update=True
        )
        st.session_state['sauvegarde_tests'][titre_actuel] = code_tests
        
        col_btn1, col_btn2 = st.columns([1, 1])
        with col_btn1:
            if st.button("▶️ Tester", key=f"btn_test_{titre_actuel}"):
                st.session_state['validation_result'][titre_actuel] = None
                old_stdout = sys.stdout
                redirected_output = StringIO()
                sys.stdout = redirected_output
                try:
                    local_scope = {}
                    full_code = st.session_state['sauvegarde_codes'][titre_actuel] + "\n\n" + st.session_state['sauvegarde_tests'][titre_actuel]
                    exec(full_code, {}, local_scope)
                    res = redirected_output.getvalue()
                    st.session_state['console_output'][titre_actuel] = res if res else "(Pas de sortie print)"
                except Exception as e:
                    st.session_state['console_output'][titre_actuel] = f"❌ Erreur : {e}"
                finally:
                    sys.stdout = old_stdout

        with col_btn2:
            if st.button("🚀 Soumettre", key=f"btn_submit_{titre_actuel}", type="primary"):
                try:
                    local_scope = {}
                    exec(st.session_state['sauvegarde_codes'][titre_actuel], {}, local_scope)
                    func_name = exercice['nom_fonction']
                    
                    if func_name not in local_scope:
                        st.session_state['validation_result'][titre_actuel] = {'error': f"Fonction '{func_name}' introuvable."}
                    else:
                        ma_fonction = local_scope[func_name]
                        score = 0
                        failures = []
                        valid_tests = exercice['tests_validation']
                        for test in valid_tests:
                            try:
                                args = test['args']
                                if not isinstance(args, (list, tuple)): args = [args]
                                res = ma_fonction(*args)
                                if res == test['expected']:
                                    score += 1
                                else:
                                    failures.append({'input': str(args), 'expected': test['expected'], 'actual': res})
                            except Exception as e:
                                failures.append({'input': str(test['args']), 'expected': "N/A", 'actual': f"Erreur: {e}"})
                        
                        st.session_state['validation_result'][titre_actuel] = {'score': score, 'total': len(valid_tests), 'failures': failures}
                        st.session_state['console_output'][titre_actuel] = "Correction terminée ⬇️"
                        
                        if score == len(valid_tests):
                            st.session_state['completed_exercises'].add(titre_actuel)
                            st.rerun() 

                except Exception as e:
                     st.session_state['console_output'][titre_actuel] = f"Erreur critique: {e}"

    with row2_col1:
        st.subheader("Sortie console")
        st.code(st.session_state['console_output'][titre_actuel], language="text")

    res = st.session_state['validation_result'][titre_actuel]
    if res:
        st.divider()
        if 'error' in res:
            st.error(res['error'])
        else:
            score, total = res['score'], res['total']
            st.metric("Score", f"{score}/{total}")
            if score == total:
                st.success("Bravo ! Exercice validé.")
                st.balloons()
            elif res['failures']:
                with st.expander("Voir les erreurs"):
                    st.write(res['failures'])


# ==============================================================================
# 3. ZONE ÉTUDIANT
# ==============================================================================
def interface_etudiant():
    init_session_state()
    
    # CHARGEMENT DEPUIS SUPABASE
    all_exos = load_exercices()
    
    active_exos = [e for e in all_exos if e.get('active', True)]
    final_exos = active_exos[:5]

    if not final_exos:
        st.warning("Aucun exercice disponible pour le moment.")
        return

    tab_titles = []
    for exo in final_exos:
        titre = exo['titre']
        if titre in st.session_state['completed_exercises']:
            titre += " ✅"
        tab_titles.append(titre)

    tabs = st.tabs(tab_titles)
    for i, tab in enumerate(tabs):
        with tab:
            afficher_exercice(final_exos[i])

# ==============================================================================
# 4. ZONE PROFESSEUR (Adaptée pour Supabase)
# ==============================================================================
def interface_prof():
    st.header("🍎 Zone Professeur")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    if not st.session_state['logged_in']:
        mdp = st.text_input("Mot de passe", type="password")
        if st.button("Se connecter"):
            if mdp == ADMIN_PASSWORD:
                st.session_state['logged_in'] = True
                st.rerun()
            else:
                st.error("Mot de passe incorrect")
        return

    col_logout, _ = st.columns([1, 5])
    with col_logout:
        if st.button("Se déconnecter"):
            st.session_state['logged_in'] = False
            st.rerun()

    tab_list, tab_create = st.tabs(["📂 Gérer les exercices", "➕ Créer un exercice"])
    exercices = load_exercices()

    # --- ONGLET 1 : VISUALISATION & ÉDITION ---
    with tab_list:
        if not exercices:
            st.info("Aucun exercice.")
        else:
            titres = [e['titre'] for e in exercices]
            choix_edit = st.selectbox("Sélectionnez un exercice :", titres)
            
            # On récupère l'exercice complet (avec son ID supabase)
            idx = titres.index(choix_edit)
            exo = exercices[idx]
            exo_id = exo['id'] # IMPORTANT pour l'update

            st.markdown("---")
            with st.expander(f"👁️ Aperçu : {exo['titre']}", expanded=True):
                etat = "🟢 Visible" if exo.get('active', True) else "🔴 Caché"
                st.caption(f"État actuel : {etat} (ID: {exo_id})")
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.info(exo['description'])
                with c2:
                    st.markdown(f"**Fonction :** `{exo['nom_fonction']}({', '.join(exo['args'])})`")

            st.markdown("---")
            st.subheader("✏️ Modifier cet exercice")

            with st.form(f"form_edit_{exo_id}"):
                col_active, col_titre = st.columns([1, 3])
                with col_active:
                    new_active = st.checkbox("Visible ?", value=exo.get('active', True))
                with col_titre:
                    new_titre = st.text_input("Titre", value=exo['titre'])
                
                new_func = st.text_input("Nom Fonction", value=exo['nom_fonction'])
                new_args = st.text_input("Arguments", value=", ".join(exo['args']))
                new_desc = st.text_area("Description", value=exo['description'])
                new_tests_visibles = st.text_area("Tests Visibles", value=exo['tests_par_defaut'])
                
                tests_str_val = pprint.pformat(exo['tests_validation'], indent=2)
                new_tests_caches = st.text_area("Tests Validation (List[Dict])", value=tests_str_val, height=200)

                st.write("")
                col_save, col_del = st.columns([1, 1])
                with col_save:
                    submitted_save = st.form_submit_button("💾 Enregistrer")
                with col_del:
                    submitted_delete = st.form_submit_button("🗑️ Supprimer", type="primary")

            if submitted_delete:
                if delete_exercice(exo_id): # APPEL SUPABASE
                    st.success("Exercice supprimé !")
                    st.rerun()

            if submitted_save:
                try:
                    args_list = [a.strip() for a in new_args.split(",") if a.strip()]
                    validation_data = ast.literal_eval(new_tests_caches)
                    if not isinstance(validation_data, list): raise ValueError("Doit être une liste")

                    # Données pour Supabase
                    updated_data = {
                        "titre": new_titre,
                        "description": new_desc,
                        "nom_fonction": new_func,
                        "args": args_list, # Supabase accepte la liste directe si type jsonb
                        "tests_par_defaut": new_tests_visibles,
                        "tests_validation": validation_data,
                        "active": new_active
                    }
                    
                    if update_exercice(exo_id, updated_data): # APPEL SUPABASE
                        st.success("Modifications enregistrées !")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erreur validation données : {e}")

    # --- ONGLET 2 : CRÉATION ---
    with tab_create:
        st.subheader("Nouvel Exercice")
        with st.form("form_create"):
            t_active = st.checkbox("Visible ?", value=True)
            t_titre = st.text_input("Titre")
            t_func = st.text_input("Nom Fonction")
            t_args = st.text_input("Arguments (ex: n, liste)")
            t_desc = st.text_area("Description")
            t_visibles = st.text_area("Tests Visibles")
            
            default_val = """[
    {"args": [1, 2], "expected": 3}
]"""
            t_caches = st.text_area("Tests Validation", value=default_val)
            
            if st.form_submit_button("Créer l'exercice"):
                try:
                    args_list = [a.strip() for a in t_args.split(",") if a.strip()]
                    val_data = ast.literal_eval(t_caches)
                    
                    new_exo = {
                        "titre": t_titre,
                        "description": t_desc,
                        "nom_fonction": t_func,
                        "args": args_list,
                        "tests_par_defaut": t_visibles,
                        "tests_validation": val_data,
                        "active": t_active
                    }
                    
                    if add_exercice(new_exo): # APPEL SUPABASE
                        st.success("Exercice créé !")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

# ==============================================================================
# 5. MAIN
# ==============================================================================
def main():
    st.sidebar.title("Navigation")
    app_mode = st.sidebar.radio("Aller vers :", ["🎓 Espace Étudiant", "🍎 Espace Professeur"])
    st.sidebar.markdown("---")
    
    if app_mode == "🎓 Espace Étudiant":
        interface_etudiant()
    else:
        interface_prof()

if __name__ == "__main__":
    main()
