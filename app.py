from flask import Flask, redirect, request, session, render_template, jsonify, url_for
import requests
import os
from dotenv import load_dotenv
from functions import evaluate_job, analyze_sections
import nest_asyncio
import asyncio
import json
from bs4 import BeautifulSoup
import re

# Применяем nest_asyncio для корректной работы asyncio.run в синхронном Flask
nest_asyncio.apply()

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev_key')

# Ваши учетные данные от HH
CLIENT_ID = os.getenv('HH_CLIENT_ID')
CLIENT_SECRET = os.getenv('HH_CLIENT_SECRET')
REDIRECT_URI = os.getenv('HH_REDIRECT_URI')

# ========================
# 🔹 Refresh access token
# ========================
def refresh_access_token():
    refresh_token = session.get('refresh_token')
    if not refresh_token:
        return None
    token_url = "https://api.hh.ru/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token
    }
    response = requests.post(token_url, data=data, headers=headers)
    token_json = response.json()
    if "access_token" in token_json:
        session['access_token'] = token_json['access_token']
        session['refresh_token'] = token_json['refresh_token']
        session['token_expires_in'] = token_json['expires_in']
        return token_json['access_token']
    return None

# ========================
# 🔹 Index UI (only after auth)
# ========================
@app.route('/')
def index():
    if 'access_token' not in session:
        return redirect('/login')
    return render_template('index.html')

# ========================
# 🔹 Start login flow
# ========================
@app.route('/login')
def login():
    hh_auth_url = (
        f"https://hh.ru/oauth/authorize?"
        f"response_type=code&client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
    )
    return redirect(hh_auth_url)

# ========================
# 🔹 Handle callback from HH with ?code=
# ========================
@app.route('/callback')
def callback():
    code = request.args.get('code')
    error = request.args.get('error')

    if error:
        return f"Access denied: {error}", 403

    if not code:
        return "Authorization code not provided", 400

    # Exchange code for tokens
    token_url = "https://api.hh.ru/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI
    }

    response = requests.post(token_url, data=data, headers=headers)
    token_json = response.json()

    if "access_token" not in token_json:
        return f"Token exchange failed: {token_json}", 400

    # Store tokens in session
    session['access_token'] = token_json['access_token']
    session['refresh_token'] = token_json['refresh_token']
    session['token_expires_in'] = token_json['expires_in']

    return redirect(url_for('index'))

@app.route('/api/me')
def get_me():
    access_token = session.get('access_token')
    if not access_token:
        return jsonify({"error": "Unauthorized"}), 401

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "ApplicantAnalyzer/1.0"
    }

    employer_id = "1391819"
    url = f"https://api.hh.ru/vacancies?employer_id={employer_id}"
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return jsonify({"error": "Failed to fetch vacancies", "details": response.json()}), response.status_code

    return jsonify(response.json())

# ========================
# 🔹 Get vacancies (using HH API and session token)
# ========================
@app.route('/api/hh_vacancies', methods=['GET'])
def get_hh_vacancies():
    access_token = session.get('access_token')
    if not access_token:
        return jsonify({"error": "Unauthorized"}), 401

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "ApplicantAnalyzer/1.0"
    }

    # Получаем информацию о текущем пользователе, чтобы извлечь employer_id
    me_url = "https://api.hh.ru/me"
    me_response = requests.get(me_url, headers=headers)

    if me_response.status_code == 401:  # Токен может быть просрочен
        access_token = refresh_access_token()
        if not access_token:
            return jsonify({"error": "Failed to refresh token"}), 401
        headers["Authorization"] = f"Bearer {access_token}"
        me_response = requests.get(me_url, headers=headers)

    if me_response.status_code != 200:
        return jsonify({"error": f"Failed to fetch user info: {me_response.text}"}), me_response.status_code

    employer_id = me_response.json().get('employer', {}).get('id')
    if not employer_id:
        return jsonify({"error": "Employer ID not found for the current user"}), 400

    # Запрашиваем вакансии с использованием employer_id
    vacancies_url = f"https://api.hh.ru/vacancies?employer_id={employer_id}"
    response = requests.get(vacancies_url, headers=headers)

    if response.status_code == 401:  # Токен может быть просрочен
        access_token = refresh_access_token()
        if not access_token:
            return jsonify({"error": "Failed to refresh token"}), 401
        headers["Authorization"] = f"Bearer {access_token}"
        response = requests.get(vacancies_url, headers=headers)

    if response.status_code != 200:
        return jsonify({"error": f"Failed to fetch vacancies: {response.text}"}), response.status_code

    vacancies = response.json().get('items', [])
    vacancy_list = [{"id": v['id'], "name": v['name']} for v in vacancies]
    return jsonify({"vacancies": vacancy_list})

# 
# 
# 

@app.route('/api/vacancy_description', methods=['GET'])
def get_vacancy_description():
    access_token = session.get('access_token')
    if not access_token:
        return jsonify({"error": "Unauthorized"}), 401

    vacancy_id = request.args.get('vacancy_id')
    if not vacancy_id:
        return jsonify({"error": "Vacancy ID not provided"}), 400

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "ApplicantAnalyzer/1.0"
    }

    vacancy_url = f"https://api.hh.ru/vacancies/{vacancy_id}"
    response = requests.get(vacancy_url, headers=headers)

    if response.status_code == 401:
        access_token = refresh_access_token()
        if not access_token:
            return jsonify({"error": "Failed to refresh token"}), 401
        headers["Authorization"] = f"Bearer {access_token}"
        response = requests.get(vacancy_url, headers=headers)

    if response.status_code == 404:
        return jsonify({"error": f"Vacancy with ID {vacancy_id} not found or inaccessible"}), 404
    if response.status_code != 200:
        return jsonify({"error": f"Failed to fetch vacancy: {response.text}"}), response.status_code

    vacancy = response.json()
    description = vacancy.get('description', '')

    # Очистка HTML-тегов и преобразование в читаемый текст
    if description:
        # Парсим HTML с помощью BeautifulSoup
        soup = BeautifulSoup(description, 'html.parser')
        
        # Удаляем скрипты и стили, если они есть
        for script_or_style in soup(['script', 'style']):
            script_or_style.decompose()
        
        # Получаем текст
        text = soup.get_text(separator='\n')
        
        # Удаляем лишние пробелы и пустые строки
        lines = [line.strip() for line in text.splitlines()]
        cleaned_text = '\n'.join(line for line in lines if line)
        
        # Заменяем множественные переносы строк на одиночные
        cleaned_text = re.sub(r'\n\s*\n+', '\n\n', cleaned_text)
    else:
        cleaned_text = ''

    return jsonify({"description": cleaned_text})

# ========================
# 🔹 Get applicants (using HH API and session token)
# ========================
@app.route('/api/hh_applicants', methods=['GET'])
def get_hh_applicants():
    access_token = session.get('access_token')
    print(f"Access token: {access_token}")
    if not access_token:
        print("Ошибка: access_token отсутствует в сессии")
        return jsonify({"error": "Unauthorized"}), 401

    vacancy_id = request.args.get('vacancy_id')
    if not vacancy_id:
        print("Ошибка: vacancy_id не предоставлен")
        return jsonify({"error": "Vacancy ID not provided"}), 400

    headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "ApplicantAnalyzer/1.0"
    }

    # Проверяем, существует ли вакансия
    vacancy_url = f"https://api.hh.ru/vacancies/{vacancy_id}"
    vacancy_response = requests.get(vacancy_url, headers=headers)
    if vacancy_response.status_code == 404:
        return jsonify({"error": f"Vacancy with ID {vacancy_id} not found or inaccessible"}), 404
    if vacancy_response.status_code == 401:
        print("Токен недействителен, пытаемся обновить")
        access_token = refresh_access_token()
        if not access_token:
            print("Не удалось обновить токен")
            return jsonify({"error": "Failed to refresh token"}), 401
        headers["Authorization"] = f"Bearer {access_token}"
        vacancy_response = requests.get(vacancy_url, headers=headers)
    if vacancy_response.status_code != 200:
        return jsonify({"error": f"Failed to verify vacancy: {vacancy_response.text}"}), vacancy_response.status_code

    # Получаем список коллекций
    negotiations_url = "https://api.hh.ru/negotiations"
    params = {"vacancy_id": str(vacancy_id)}
    response = requests.get(negotiations_url, headers=headers, params=params)
    if response.status_code == 401:
        print("Токен недействителен для negotiations, пытаемся обновить")
        access_token = refresh_access_token()
        if not access_token:
            print("Не удалось обновить токен для negotiations")
            return jsonify({"error": "Failed to refresh token"}), 401
        headers["Authorization"] = f"Bearer {access_token}"
        response = requests.get(negotiations_url, headers=headers, params=params)
    if response.status_code == 404:
        return jsonify({"applicants": []}), 200
    if response.status_code != 200:
        return jsonify({"error": f"Failed to fetch collections: {response.text}"}), response.status_code

    # Парсим список коллекций
    collections_data = response.json()
    collections = collections_data.get('collections', [])
    applicants = []

    # Перебираем все коллекции
    for collection in collections:
        collection_url = collection.get('url')
        collection_name = collection.get('name')
        counters = collection.get('counters', {})
        total_applicants = counters.get('total', 0)

        print(f"Processing collection '{collection_name}' with {total_applicants} applicants")

        if total_applicants == 0:
            print(f"Коллекция '{collection_name}' не содержит откликов")
            continue

        # Handle pagination
        page = 0
        while True:
            paginated_url = f"{collection_url}&page={page}&per_page=20"
            print(f"Получаем отклики из коллекции '{collection_name}' по URL: {paginated_url}")
            
            # Запрашиваем отклики для каждой коллекции
            collection_response = requests.get(paginated_url, headers=headers)
            print(f"Collection '{collection_name}' API response status: {collection_response.status_code}")

            # Сохраняем ответ API в файл
            file_name = f"collection_{collection_name}_{vacancy_id}_page_{page}.json"
            # with open(file_name, "w", encoding="utf-8") as f:
            #     f.write(collection_response.text)

            if collection_response.status_code == 401:
                print(f"Токен недействителен для коллекции '{collection_name}', пытаемся обновить")
                access_token = refresh_access_token()
                if not access_token:
                    print("Не удалось обновить токен")
                    return jsonify({"error": "Failed to refresh token"}), 401
                headers["Authorization"] = f"Bearer {access_token}"
                collection_response = requests.get(paginated_url, headers=headers)
                print(f"Retry Collection '{collection_name}' API response status: {collection_response.status_code}")
                # with open(f"retry_{file_name}", "w", encoding="utf-8") as f:
                    # f.write(collection_response.text)

            if collection_response.status_code != 200:
                print(f"Ошибка загрузки откликов из коллекции '{collection_name}': {collection_response.text}")
                break  # Пропускаем коллекцию при ошибке

            # Парсим отклики
            collection_data = collection_response.json()
            items = collection_data.get('items', [])
            
            for item in items:
                resume = item.get('resume', {})
                employer_state = item.get('employer_state', {})
                applicant = {
                    'resume_id': resume.get('id'),
                    'first_name': resume.get('first_name'),
                    'last_name': resume.get('last_name'),
                    'status': employer_state.get('id', collection.get('id')),  # Use employer_state if available
                    'status_name': employer_state.get('name', collection_name),
                    'resume_url': resume.get('url'),
                    'created_at': item.get('created_at'),
                    'updated_at': item.get('updated_at'),
                    'age': resume.get('age'),
                    'area': resume.get('area', {}).get('name'),
                    'title': resume.get('title'),
                    'total_experience_months': resume.get('total_experience', {}).get('months')
                }
                applicants.append(applicant)

            # Check for pagination
            pages = collection_data.get('pages', 1)
            page += 1
            if page >= pages:
                break

    # Возвращаем список кандидатов
    returned_applicants = jsonify({"applicants": applicants})
    print("Answer: ")
    print(returned_applicants)
    print("End answer")
    return returned_applicants, 200

# ========================
# 🔹 Extract requirements from job description
# ========================
@app.route('/api/requirements', methods=['POST'])
def extract_requirements():
    data = request.get_json()
    job_text = data.get('text')
    if not job_text:
        return jsonify({"error": "Job description not provided"}), 400
    try:
        requirements = asyncio.run(evaluate_job(job_text))
        # Сохраняем требования в сессии
        session['job_requirements'] = requirements
        return jsonify({"requirements": requirements})
    except Exception as e:
        return jsonify({"error": f"Failed to extract requirements: {str(e)}"}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze_applicant():
    try:
        selected_applicant_id = request.form.get('applicant_id')
        file = request.files.get('file')
        access_token = session.get('access_token')

        # Получаем требования из сессии
        job_requirements = session.get('job_requirements', {
            "must_have": [],
            "nice_to_have": []
        })

        # Выводим требования для проверки
        print("Обязательные требования:", job_requirements['must_have'])
        print("Желательные требования:", job_requirements['nice_to_have'])

        if file:
            # TODO: Анализировать PDF
            result = "PDF analysis not implemented yet"
            return jsonify({"analysis": result})

        elif selected_applicant_id:
            if not access_token:
                return jsonify({"error": "Unauthorized: No access token"}), 401

            headers = {
                "Authorization": f"Bearer {access_token}",
                "User-Agent": "ApplicantAnalyzer/1.0"
            }

            # Запрашиваем полное резюме по resume_id
            print("ID: ", selected_applicant_id)
            resume_url = f"https://api.hh.ru/resumes/{selected_applicant_id}"
            try:
                resume_response = requests.get(resume_url, headers=headers)
            except requests.RequestException as e:
                print(f"Ошибка запроса к HH.ru: {str(e)}")
                return jsonify({"error": f"Failed to fetch resume: {str(e)}"}), 500

            if resume_response.status_code == 401:
                access_token = refresh_access_token()
                if not access_token:
                    return jsonify({"error": "Failed to refresh token"}), 401
                headers["Authorization"] = f"Bearer {access_token}"
                try:
                    resume_response = requests.get(resume_url, headers=headers)
                except requests.RequestException as e:
                    print(f"Ошибка повторного запроса к HH.ru: {str(e)}")
                    return jsonify({"error": f"Failed to fetch resume: {str(e)}"}), 500

            if resume_response.status_code != 200:
                return jsonify({"error": f"Failed to fetch resume: {resume_response.text}"}), resume_response.status_code

            # Парсим резюме
            try:
                resume_data = resume_response.json()
            except ValueError as e:
                print(f"Ошибка парсинга JSON резюме: {str(e)}")
                return jsonify({"error": f"Invalid resume data: {str(e)}"}), 500

            # Формируем секции для анализа
            sections = {}

            # Навыки (существующая логика)
            skills = []
            if resume_data.get('skill_set'):
                skills.extend(resume_data['skill_set'])
            if resume_data.get('skills'):
                skills.append(resume_data['skills'])
            sections['skills'] = ' '.join(skills) if skills else 'Нет данных о навыках'

            # Опыт работы (существующая логика)
            if resume_data.get('experience'):
                for exp in resume_data['experience']:
                    company = exp.get('company', 'Неизвестная компания')
                    description = exp.get('description', '') or 'Нет описания'
                    position = exp.get('position', 'Не указана должность')
                    start = exp.get('start', 'Не указан период')
                    end = exp.get('end', 'по настоящее время')
                    section_name = f"experience_{company}"
                    sections[section_name] = f"Должность: {position}\nПериод: {start} - {end}\nОписание: {description}"

            # Новые секции из списка
            # Общая информация
            general_info = []
            if resume_data.get('first_name') or resume_data.get('last_name'):
                general_info.append(f"Имя: {resume_data.get('first_name', '')} {resume_data.get('last_name', '')}")
            if resume_data.get('age'):
                general_info.append(f"Возраст: {resume_data.get('age')}")
            if resume_data.get('gender'):
                general_info.append(f"Пол: {resume_data.get('gender', {}).get('name', 'Не указан')}")
            sections['general_information'] = '\n'.join(general_info) if general_info else 'Нет данных'

            # Желаемая должность и зарплата
            preferred_job = []
            if resume_data.get('title'):
                preferred_job.append(f"Желаемая должность: {resume_data['title']}")
            if resume_data.get('salary'):
                salary = resume_data['salary']
                amount = salary.get('amount', 'Не указана')
                currency = salary.get('currency', '')
                preferred_job.append(f"Желаемая зарплата: {amount} {currency}")
            sections['perefered_job'] = '\n'.join(preferred_job) if preferred_job else 'Нет данных'

            # Сопроводительное письмо
            sections['cover_letter'] = resume_data.get('cover_letter', 'Нет данных')

            # Образование
            education = []
            if resume_data.get('education'):
                for edu in resume_data['education'].get('primary', []):
                    name = edu.get('name', 'Не указано заведение')
                    year = edu.get('year', 'Не указан год')
                    specialty = edu.get('specialty', 'Не указана специальность')
                    education.append(f"Учреждение: {name}\nГод окончания: {year}\nСпециальность: {specialty}")
                sections['education'] = '\n'.join(education) if education else 'Нет данных'
            else:
                sections['education'] = 'Нет данных'

            # Опыт вождения
            driving_experience = []
            if resume_data.get('driver_license'):
                licenses = resume_data['driver_license']
                categories = [lic.get('category', '') for lic in licenses]
                driving_experience.append(f"Категории прав: {', '.join(categories) if categories else 'Не указаны'}")
            sections['driving_experience'] = '\n'.join(driving_experience) if driving_experience else 'Нет данных'

            # Дополнительная информация
            additional_info = []
            if resume_data.get('about'):
                additional_info.append(f"О себе: {resume_data['about']}")
            if resume_data.get('language'):
                languages = [f"{lang.get('name', 'Не указан язык')} ({lang.get('level', {}).get('name', 'Не указан уровень')})" 
                            for lang in resume_data['language']]
                additional_info.append(f"Языки: {', '.join(languages) if languages else 'Не указаны'}")
            sections['additional_information'] = '\n'.join(additional_info) if additional_info else 'Нет данных'

            # История общения с кандидатом
            sections['conntacts_with_candidate'] = resume_data.get('contacts_history', 'Нет данных')

            # Сохраняем резюме (для отладки)
            output_dir = "resumes"
            os.makedirs(output_dir, exist_ok=True)
            file_path = os.path.join(output_dir, f"resume_{selected_applicant_id}.json")
            # with open(file_path, "w", encoding="utf-8") as f:
            #     json.dump(resume_data, f, ensure_ascii=False, indent=2)

            # Анализируем секции
            try:
                responses = asyncio.run(analyze_sections(job_requirements, sections))
                # print("Ответы ИИ:", responses)
                analyze_results = [response.choices[0].message.tool_calls[0].function.arguments for response in responses]
                print(analyze_results)
                # Обрабатываем результаты
                analysis_result = []
                all_requirements = job_requirements['must_have'] + job_requirements['nice_to_have']
                satisfied_requirements = set()
                not_satisfied_requirements = set(all_requirements)

                # Отладочный вывод для проверки требований
                print("must_have:", job_requirements['must_have'])
                print("nice_to_have:", job_requirements['nice_to_have'])
                print("All requirements:", all_requirements)
                print("Length of all_requirements:", len(all_requirements))

                # Парсим analyze_results
                for result in analyze_results:
                    try:
                        function_args = json.loads(result)
                        requirements_satisfaction = function_args.get('requirements_satisfaction', [])
                        section_name = function_args.get('section_name', 'Unknown')

                        # Отладочный вывод для каждой секции
                        print(f"Section: {section_name}, Requirements satisfaction: {requirements_satisfaction}")

                        # Проверяем каждое требование
                        for req_idx, satisfied_flag in enumerate(requirements_satisfaction):
                            if satisfied_flag and req_idx < len(all_requirements):
                                satisfied_requirements.add(all_requirements[req_idx])
                                if all_requirements[req_idx] in not_satisfied_requirements:
                                    not_satisfied_requirements.remove(all_requirements[req_idx])
                    except json.JSONDecodeError as e:
                        print(f"Ошибка парсинга JSON в analyze_results: {str(e)}")
                        continue

                # Отладочный вывод результатов
                print("Satisfied requirements:", satisfied_requirements)
                print("Not satisfied requirements:", not_satisfied_requirements)

                # Формируем результат
                # Поскольку section_name всегда Unknown, используем общее описание
                analysis_result.append(
                    f"Анализ резюме:\n"
                    f"Выполненные требования: {', '.join(satisfied_requirements) if satisfied_requirements else 'Нет'}\n"
                    f"Невыполненные требования: {', '.join(not_satisfied_requirements) if not_satisfied_requirements else 'Нет'}\n"
                )

                result = "\n".join(analysis_result) if analysis_result else "Нет данных для анализа"
            except Exception as e:
                print(f"Ошибка анализа резюме: {str(e)}")
                result = f"Ошибка анализа резюме {selected_applicant_id}: {str(e)}"

            return jsonify({"analysis": result})

        else:
            return jsonify({"error": "No applicant selected or file uploaded"}), 400

    except Exception as e:
        print(f"Необработанная ошибка в analyze_applicant: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500
    

# @app.route('/api/company_vacancies')
# def get_company_vacancies():
#     access_token = session.get('access_token')
#     if not access_token:
#         return jsonify({"error": "Unauthorized"}), 401

#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "User-Agent": "ApplicantAnalyzer/1.0"
#     }

#     employer_id = "1391819"
#     url = f"https://api.hh.ru/vacancies?employer_id={employer_id}"
#     response = requests.get(url, headers=headers)

#     if response.status_code != 200:
#         return jsonify({"error": "Failed to fetch vacancies", "details": response.json()}), response.status_code

#     return jsonify(response.json())

if __name__ == "__main__":
    app.run(debug=True)
