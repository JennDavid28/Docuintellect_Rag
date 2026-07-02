import os
import pickle
import hashlib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

MODEL_PATH = "backend/classifier.pkl"
MODEL_VERSION_PATH = "backend/classifier.version"

TRAINING_DATA = [
    # Research (expanded)
    ("scientific method hypothesis experiment peer review data collection laboratory journal article citation abstract thesis clinical trial control group statistical significance methodology findings analysis results conclusion", "Research"),
    ("research paper study survey literature review quantitative qualitative mixed methods sample population variable correlation regression hypothesis testing p-value confidence interval", "Research"),
    ("genomic sequencing protein structure neural network training dataset benchmark evaluation baseline model architecture experiment ablation study", "Research"),
    ("clinical outcomes patient cohort randomized controlled trial dosage efficacy safety pharmacokinetics biomarker longitudinal study", "Research"),
    ("published findings academic institution university grant funding peer reviewed journal impact factor citations references bibliography", "Research"),

    # Finance (expanded)
    ("revenue profit loss balance sheet quarterly earnings asset liability portfolio trading stock index bond market interest rate capital valuation tax dividend shareholder equity", "Finance"),
    ("cash flow investment yield audit fiscal budget amortization depreciation accounts receivable payable net income gross margin EBITDA operating expenses", "Finance"),
    ("financial statements income statement annual report SEC filing earnings per share market capitalization return on investment risk assessment hedge fund private equity", "Finance"),
    ("mortgage loan interest payment principal amortization credit score debt ratio refinancing foreclosure bank lending borrower lender", "Finance"),
    ("cryptocurrency blockchain bitcoin ethereum DeFi token NFT exchange wallet transaction hash proof of stake mining", "Finance"),

    # Legal (expanded)
    ("contract agreement clause liability lawsuit litigation compliance attorney court regulations statute trademark patent copyright arbitration breach jurisdiction", "Legal"),
    ("non-disclosure confidentiality indemnification intellectual property rights settlement damages injunction subpoena deposition plaintiff defendant verdict appeal", "Legal"),
    ("employment law termination discrimination harassment wrongful dismissal severance non-compete clause labor union collective bargaining EEOC", "Legal"),
    ("corporate governance board directors fiduciary duty shareholder rights merger acquisition due diligence regulatory compliance SEC antitrust", "Legal"),
    ("privacy policy GDPR data protection consent personal information data breach notification terms of service end user license agreement", "Legal"),

    # Education (expanded)
    ("student teacher syllabus curriculum lecture university classroom assignment grade exam study semester textbook pedagogy diploma degree enrollment", "Education"),
    ("learning outcomes assessment rubric online course e-learning LMS Moodle Canvas Blackboard educational technology blended learning flipped classroom", "Education"),
    ("school district standardized testing SAT ACT GRE GMAT TOEFL academic performance dropout graduation rate special education IEP", "Education"),
    ("professional development training workshop certification continuing education skills gap competency framework mentoring coaching leadership program", "Education"),
    ("kindergarten elementary middle high school teacher principal superintendent curriculum standards Common Core STEM STEAM extracurricular", "Education"),
    ("notes syllabus assignment lecture grade exam study", "Education"),
    ("subject related study material textbook ", "Education"),

    # Technology (expanded)
    ("software code programming developer database API server application cloud network computing AI machine learning model backend frontend system engineering", "Technology"),
    ("python javascript typescript react angular vue node.js docker kubernetes microservices REST GraphQL CI/CD DevOps git repository deployment", "Technology"),
    ("cybersecurity firewall encryption SSL TLS vulnerability penetration testing SIEM SOC threat intelligence malware ransomware phishing zero-day", "Technology"),
    ("data science pandas numpy scikit-learn tensorflow pytorch deep learning neural network computer vision NLP transformer BERT GPT embedding", "Technology"),
    ("product roadmap agile scrum sprint backlog user story acceptance criteria MVP A/B testing product-market fit KPIs OKRs SaaS platform", "Technology"),
    ("cloud computing AWS Azure GCP serverless lambda containers orchestration infrastructure IaC terraform ansible monitoring observability", "Technology"),
]

def _training_data_hash() -> str:
    """Return a short hash of the training data so we only retrain when
    the training corpus actually changes — not on every process restart."""
    raw = "".join(f"{t}{l}" for t, l in TRAINING_DATA).encode()
    return hashlib.md5(raw).hexdigest()[:12]

def train_classifier():
    texts = [d[0] for d in TRAINING_DATA]
    labels = [d[1] for d in TRAINING_DATA]

    pipeline = Pipeline([
        ('vectorizer', TfidfVectorizer(
            ngram_range=(1, 3),
            stop_words='english',
            max_features=20000,
            sublinear_tf=True,
            min_df=1
        )),
        ('classifier', LogisticRegression(
            max_iter=1000,
            C=5.0,
            class_weight='balanced',
            random_state=42
        ))
    ])

    pipeline.fit(texts, labels)
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(pipeline, f)
    # Save hash so next import knows the model is current
    with open(MODEL_VERSION_PATH, 'w') as f:
        f.write(_training_data_hash())
    return pipeline

def get_classifier():
    """Load from disk when available and up-to-date; retrain otherwise."""
    current_hash = _training_data_hash()
    saved_hash = ""
    if os.path.exists(MODEL_VERSION_PATH):
        try:
            with open(MODEL_VERSION_PATH, 'r') as f:
                saved_hash = f.read().strip()
        except OSError:
            pass

    if os.path.exists(MODEL_PATH) and saved_hash == current_hash:
        try:
            with open(MODEL_PATH, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass  # corrupt pickle — fall through to retrain

    return train_classifier()

def classify_document(text_content: str) -> str:
    if not text_content or len(text_content.strip()) < 10:
        return "Technology"
    try:
        # Use first 2000 chars for classification speed
        pipeline = get_classifier()
        prediction = pipeline.predict([text_content[:2000]])
        return prediction[0]
    except Exception:
        return "Research"

# Train once at import time only if the model is missing or stale.
# This replaces the old "delete-and-retrain-every-import" pattern that
# added several seconds to every server startup and every hot reload.
get_classifier()
