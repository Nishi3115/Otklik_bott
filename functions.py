from openai import OpenAI, AsyncOpenAI
from openai import AsyncAzureOpenAI
from dotenv import load_dotenv
import os
import json
import pdfplumber
from os import listdir
from os.path import isfile, join
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Spacer, SimpleDocTemplate
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfReader, PdfWriter
import io
import os
import mypy
import re
from functools import reduce
from typing import List

load_dotenv()

# Инициализация асинхронного клиента Azure OpenAI
openai = AsyncAzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),  # Ключ API из Azure
    api_version="2024-02-15-preview",           #
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")  # Конечная точка Azure
)

job_text = """
Быстрорастущая компания в сфере IT, меняющая рынок Узбекистана. Ищет лидера C&B с релокацией в Ташкент.

Что нужно делать:
• Управление бюджетом ФОТ и HR Бюджетами по холдингу.
• Разработка систем мотивации C-level (анализ, предложения, реализация).
• Бенчмаркинг рынков труда (особенно Узбекистана) + нетворкинг.
• Автоматизация C&B процессов.
• Руководство командой C&B и функциональное управление C&B в БЮ.
Что ждем от вас:
• Опыт C&B на руководящей позиции.
• Успешный опыт разработки систем мотивации.
• Сильные аналитические навыки, Excel.
• Насмотренность лучших практик C&B.
• Лидерские качества, стрессоустойчивость.
Что предлагаем:
• Конкурентная ЗП + релокация + премия.
• ДМС.
• Рост, развитие, влияние
"""

job_text = """
Крупной международной компании специализирующееся на информационной безопасности нужен Business development manager.

Условия:
Конкурентоспособная ЗП плюс бонусная система
Полный пакет добровольного медицинского страхования
Гибридный режим, позволяющий сочетать удаленную работу с офисными днями

Основные обязанности
- Подготовка стратегии выхода на рынок в соответствующей территории (продукты, клиенты, партнерства)
- Установление регулярных бизнес-коммуникаций с ключевыми вендорами и заказчиками в области информационной безопасности
- Подготовка и защита ресурсного плана (инженеры, их компетенции, планируемая утилизация)
- Участие в переговорах в роли технического консультанта в процессе пресейла
- Формализация требований клиентов для выбора наилучшего решения
- Написание технических требований и описаний продуктов
- Поддержание и развитие отношений с техническими экспертами профильных вендоров
- Участие в маркетинговых мероприятиях компании, включая выступления в качестве докладчика

Специальные знания и навыки
- Образование в области информационной безопасности или IT
- Опыт работы в ИБ не менее 5 лет в роли заказчика, интегратора, вендора или дистрибьютора
- Знание нормативной базы в области защиты информации, законодательства и стандартов
- Знание решений в области защиты информации
- Опыт применения технологий продаж в корпоративном сегменте на практике будет плюсом
- Навыки проведения публичных выступлений и презентаций
- Опыт работы в распределенной команде
"""

tools_bygpt = [{
    "type": "function",
    "function": {
        "name": "analyze_section",
        "description": "Compare CV section with given requirements and decide if the requirement was satisfied.",
        "parameters": {
            "type": "object",
            "properties": {
                "requirements_satisfaction": {
                    "type": "array",
                    "description": "Array of booleans showing True if requirement was satisfied, False if not. ARRAY LENGTH MUST ALWAYS MATCH REQUIREMENTS COUNT",
                    "items": {
                        "type": "boolean",
                        "description": "True if this requirement is satisfied False if not. NEVER SKIP REQUIREMENT"
                    }
                    },
            },
            "required": ["satisfaction_array"]
        }
    }
},
{
    "type" : "function",
    "function":{
        "name": "structure_cv",
        "description": (
                        # "Break down the resume text into resume structure blocks. Give offests token where the CV should be separated into requried information"
                        # "If you are unsure to which section part belongs, SECTIONS CAN OVERLAP"
                        # "Use texts as Сопроводительное письмо, Желаемая должность и зарплата, Опыт работы — , Образование, Навыки, Опыт вождения, Дополнительная информация as section begining identifiers"
                        "Break down the resume text into resume structure blocks. Give offests string positions where the CV should be separated into requried information"
                        "If you are unsure to which section part belongs, SECTIONS CAN OVERLAP"
                        "Use texts as Сопроводительное письмо, Желаемая должность и зарплата, Опыт работы — , Образование, Навыки, Опыт вождения, Дополнительная информация as section begining identifiers"
                        ),
        "parameters" : {
            "type": "object",
            "properties":{
                "general_information":{
                            "type": "array",
                            "description": ("An array of [start, end] string indices indicating the section in CV."
                                            "General information about the candidate given in the begining of the resume"),
                            "items": {
                            "type": "number",
                            },
                            "minItems": 2,
                            "maxItems": 2
                        },
                "cover_letter":{
                            "type": "array",
                            "description": ("An array of [start, end] string indices indicating the section section in CV."
                                            "Cover letter of applicant"
                                            "Information about perfereable position with deatils like time schedule, specialization, etc."
                                            "List of educations and qualification that the applicant listed"
                                            "List of skills that the applicant listed. This might include language knowledge, hard skills, soft skills, etc."
                                            "additional information that applicant mentioned"),
                            "items": {
                            "type": "number",
                            },
                            "minItems": 2,
                            "maxItems": 2
                        },
                "perfered_job":{
                            "type": "array",
                            "description": ("An array of [start, end] string indices indicating the section in CV.""General information about the candidate given in the begining of the resume"
                                            "Information about perfereable position with deatils like time schedule, specialization, etc."),
                            "items": {
                            "type": "number",
                            },
                            "minItems": 2,
                            "maxItems": 2
                            },
                "jobs":{
                    "type": "array",
                    "description": ("previous and current jobs"),
                    "items": {
                        "type": "array",
                        "description": ("An array of [start, end] string indices indicating the job name, experience, details info section in CV."),
                        "items": {
                        "type": "number",
                        },
                        }
                    },
                "education":{
                    "type": "array",
                    "description": ("An array of [start, end] string indices indicating the education and qualification info section in CV."
                                    "List of educations and qualification that the applicant listed"),
                    "items": {
                    "type": "number",
                    },
                    "minItems": 2,
                    "maxItems": 2
                },
                "skills" :{
                    "type": "array",
                    "description": ("An array of [start, end] string indices indicating the skills info section in CV."
                                    "List of skills that the applicant listed. This might include language knowledge, hard skills, soft skills, etc."),
                    "items": {
                    "type": "number",
                    },
                    "minItems": 2,
                    "maxItems": 2
                    },              
                "additional_information": {
                    "type": "array",
                    "description": ("An array of [start, end] string indices indicating the additional info section in CV."
                                    "additional information that applicant mentioned"),
                    "items": {
                    "type": "number",
                    },
                    "minItems": 2,
                    "maxItems": 2   
                }
                },
            "required": ["general_information, jobs"]
    },
    }
}
]

new_tools = [
    {
    "type": "function",
    "function": {
        "name": "parse_russian_job_requirements",
        "description": (
            "Парсит из описания вакансии на русском языке списки обязательных (mandatory) "
            "и желательных (optional) требований. Каждое требование включает краткое описание "
            "и подробную формулировку."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mandatory": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "details": {
                                "type": "string",
                                "description": "Подробное описание требования с абривиатурами"
                            },
                            "id":{
                                "type": "number",
                                "description": "unique integer ID of this requirement. Make it up. Make sure there are not duplicates"
                            }
                        },
                        "required": ["short", "details", "id"]
                    },
                    "description": "Список обязательных требований"
                },
                "optional": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "details": {
                                "type": "string",
                                "description": "Подробное описание требования с абривиатурами"
                            },
                            "id":{
                                "type": "number",
                                "description": "unique integer ID of this requirement. Make it up. Make sure there are not duplicates"
                            }
                        },
                        "required": ["short", "details", "id"]
                    },
                    "description": "Список желательных требований"
                }
            },
            "required": ["mandatory", "optional"]
        }
    }
},
    {
    "type" : "function",
    "function":{
        "name": "structure_cv",
        "description": ("Break down the resume text into resume structure blocks. Give offests of the string where the CV should be separated into requried information"
        "Ignore newline marks"),
        "parameters" : {
            "type": "object",
            "properties":{
                "general_information":{
                            "type": "array",
                            "description": ("An array of [start, end] pairs indicating the text slices to extract."
                                            "General information about the candidate given in the begining of the resume"),
                            "items": {
                            "type": "array",
                            "items": {
                                "type": "integer"
                            },
                            "minItems": 1,
                            "maxItems": 10
                            }
                        },
                "cover_letter":{
                            "type": "array",
                            "description": ("An array of [start, end] pairs indicating the text slices to extract."
                                            "Cover letter of applicant"),
                            "items": {
                            "type": "array",
                            "items": {
                                "type": "integer"
                            },
                            "minItems": 1,
                            "maxItems": 10
                            }
                        },
                "perfered_job":{
                            "type": "array",
                            "description": ("An array of [start, end] pairs indicating the text slices to extract."
                                            "Information about perfereable position with deatils like time schedule, specialization, etc."),
                            "items": {
                            "type": "array",
                            "items": {
                                "type": "integer"
                            },
                            "minItems": 1,
                            "maxItems": 10
                            }
                        },
                "jobs":{
                    "type": "array",
                    "description": ("List of previous and current jobs"),
                    "items": {
                        "type": "object",
                        "properties":{
                            "job_title": {
                                "type": "array",
                                "description": ("An array of [start, end] pairs indicating the text slices to extract."
                                                "position title"),
                                    "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "integer"
                                    },
                                    "minItems": 1,
                                    "maxItems": 10
                                    }
                            },
                            "company_name": {
                                "type": "array",
                                "description": ("An array of [start, end] pairs indicating the text slices to extract."
                                                "name of the company for given job" ),
                                    "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "integer"
                                    },
                                    "minItems": 1,
                                    "maxItems": 10
                                    }
                            },
                            "company_details": {
                                "type": "array",
                                "description": ("An array of [start, end] pairs indicating the text slices to extract."
                                                "information about the company"  ),
                                    "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "integer"
                                    },
                                    "minItems": 1,
                                    "maxItems": 10
                                    }
                            },
                            "job_details": {
                                "type": "array",
                                "description": ("An array of [start, end] pairs indicating the text slices to extract."
                                                "all details that applicant has mentioned about the job, their responsibilities, achivements."),
                                    "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "integer"
                                    },
                                    "minItems": 1,
                                    "maxItems": 10
                                    }
                            },
                            "duration_month": {
                                "type": "number",
                                "description": "month spent in this job. If the job is current, use the date of resume update which is mentioned in the end of the documnet. COUNT, NO OFSETS NEEDED" 
                            },
                            "start_date":{
                                "type": "string",
                                "description": "date of starting the job. Format: dd.mm.yyyy. e.g. 02.12.2021. FIND, NO OFSETS NEEDED"
                            }, 
                            "end_date":{
                                "type": "string",
                                "description": "date of ending the job. Format: dd.mm.yyyy. e.g. 02.12.2021. If the job is current, use the date of resume update which is mentioned in the end of the documnet. FIND, NO OFSETS NEEDED"
                            },
                            "current_job":{
                                "type": "boolean",
                                "description": "If the job is current, True (1), else False (0). DESIDE, NO OFSETS NEEDED"
                            }
                        }
                    },
                },
                "education":{
                    "type": "array",
                    "description": ("An array of [start, end] pairs indicating the text slices to extract."
                                    "List of educations and qualification that the applicant listed"),
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "integer"
                    },
                    "minItems": 1,
                    "maxItems": 10
                    }
                },
                "skills" :{
                    "type": "array",
                    "description": ("An array of [start, end] pairs indicating the text slices to extract."
                                    "List of skills that the applicant listed. This might include language knowledge, hard skills, soft skills, etc."),
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "integer"
                    },
                    "minItems": 1,
                    "maxItems": 10
                    }                    
                },
                "additional_information": {
                    "type": "array",
                    "description": ("An array of [start, end] pairs indicating the text slices to extract."
                                    "additional information that applicant mentioned"),
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "integer"
                    },
                    "minItems": 1,
                    "maxItems": 10
                    }    
                }
                },
            },
            "required": ["general_information, jobs"]
        }
    },
  {
  "type": "function",
  "function": {
    "name": "evalute_cv_part",
    "description": (
        "Compare part of resume describing the candidate with job requirements"
        "some of the requirements are named 'mandatory' and some 'optional'"
        "Return ids of requirements which were satisfied in that part if any even were"
    ),
    "parameters": {
      "type": "object",
      "properties": {
        "mandatory_met": {
          "type": "array",
          "items": {
            "type": "number",
            "description": "id of satisfied mandatory requirement. Mighty be empty",
          },
          "description": "Array of satisfied mandatory requirements ids"
        },
        "optional_met": {
          "type": "array",
          "items": {
            "type": "number",
            "description": "id of satisfied optional requirement. Might be empty",
          },
          "description": "Array of satisfied optional requirements ids"
        },
      },
      "required": [
        "mandatory_met",
        "optional_met",
      ]
    }
  }
}
]


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Извлекает текст из всех страниц PDF-файла с помощью PyPDF2.
    Возвращает текст одной строкой.
    """
    with pdfplumber.open(pdf_path) as pdf:
        text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
    return text

async def evaluate_job(job_text):
    messages = [
        {
            "role": "system",
            "content": (
                "Ты – помощник по анализу вакансий. "
                "Тебе дан текст описания вакансии на русском языке. "
                "Нужно извлечь из него два списка: обязательные (must have) "
                "и желательные (nice to have) требования. "
                "Не давай никаких пояснений и не пиши обычный текст. "
                "Если подходящих требований нет, верни пустые массивы. "
                "Желательные требования могут быть не отмечены напрямую. "
                "Можно предполагать, какие из требований желательные. "
                "Возвращай только в формате function calling."
            )
        },
        {
            "role": "user",
            "content": job_text
        }
    ]

    response = await openai.chat.completions.create(
        model="gpt-4o-mini", 
        messages=messages,
        tools=new_tools,
        tool_choice={"type": "function", "function": {"name": "parse_russian_job_requirements"}}
    )
    
    # Извлечение результата вызова функции
    tool_call = response.choices[0].message.tool_calls[0]
    function_args = json.loads(tool_call.function.arguments)
    
    # Извлечение только поля details из каждого требования
    must_have = [req["details"] for req in function_args.get("mandatory", [])]
    nice_to_have = [req["details"] for req in function_args.get("optional", [])]
    
    # Возврат требований в виде словаря
    return {
        "must_have": must_have,
        "nice_to_have": nice_to_have
    }

def map_requirements(job_requirements):
    requirement_map = {}
    for type in job_requirements:
        for requirement in job_requirements[type]:
            requirement_map[requirement['id']] = {'text': requirement['details'], 'type': type}
    return requirement_map

def reverse_map_requirements(requirement_map):
    reversed_map = {'mandatory': [], 'optional': []}
    for req_id, data in requirement_map.items():
        requirement_entry = {
            'id': req_id,
            'details': data['text'],
            'satisfied': data.get('satisfied', 0)  # default to 0 if not set
        }
        reversed_map[data['type']].append(requirement_entry)
    return reversed_map

# ================================
#               Тест
# ================================


# Step 1: Lightweight indexer using GPT-3.5-turbo with function calling
async def get_section_offsets(cv_text, model="HHAnalytics"):
    messages = [
        {"role": "system", "content": (
            "Identify offsets for these resume sections: general information, cover letter, preferred job, jobs, education, skills, additional information. "
            "Provide offsets as string indices."
            "The sections usually come in given order. You can pick the begining of section earlier and end later then identified to make sure all information is captured. Your response sections may overlap"
            "Use texts as Сопроводительное письмо, Желаемая должность и зарплата, Опыт работы — , Образование, Навыки, Опыт вождения, Дополнительная информация as section begining identifiers"
        )},
        {"role": "user", "content": cv_text}
    ]

    response = await openai.chat.completions.create(
        model=model,
        messages=messages,
        tools=tools_bygpt,
        tool_choice={"type":"function", "function":{"name":"structure_cv"}}
    )

    return response

async def analyze_sections(job_requirements: dict, sections: dict, model="gpt-4o-mini"):
    response_list = []
    # Формируем список всех требований (строки)
    requirements_list = job_requirements.get('must_have', []) + job_requirements.get('nice_to_have', [])
    # print(sections)
    # print(job_requirements)
    for section_name, content in sections.items():
        print(section_name, content)
        print('\n\n')
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional recruiter. You must analyze if the information in given CV section satisfies any of requirements. "
                    "You have to be accurate as a TOP1 recruiter would be. "
                    "STICK STRICT TO REQUIREMENTS. NO ASSUMPTIONS."
                )
            },
            {
                "role": "user",
                "content": (
                    f"REQUIREMENTS: {requirements_list}\n"
                    f"SECTION NAME: {section_name}\n"
                    f"SECTION DATA: {content}"
                )
            }
        ]

        response = await openai.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools_bygpt,
            tool_choice={"type": "function", "function": {"name": "analyze_section"}}
        )
        response_list.append(response)
    return response_list

section_map = {
    "Отклик на вакансию:" : "general_information",
    "Желаемая должность и зарплата" : "perefered_job",
    "Сопроводительное письмо" : "cover_letter",
    "Опыт работы —" : "jobs",
    "Образование" : "education",
    "Навыки" : "skills",
    "Опыт вождения" : "driving_experience",
    "Дополнительная информация" : "additional_information",
    "История общения с кандидатом" : "conntacts_with_candidate",
}

def new_create_analyzed_doc(requirements: dict, original_doc_papth: str, new_folder_path: str):
    pdfmetrics.registerFont(TTFont('Arial', 'C:\\Windows\\Fonts\\arial.ttf'))

    print('1')

    # PDF creation
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)

    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle(name='Normal', fontName='Arial', fontSize=11, leading=15)
    style_title = ParagraphStyle(name='Title', fontName='Arial', fontSize=16, spaceAfter=12)
    style_heading = ParagraphStyle(name='Heading', fontName='Arial', fontSize=14, spaceBefore=12, spaceAfter=6)

    remaped_reqs = reverse_map_requirements(requirements)

    elements = []

    print("got following remap:", remaped_reqs)

    def render_section(remaped_reqs):
        for title, data in remaped_reqs.items():
            elements.append(Paragraph(title, style_heading))
            for item in data:
                elements.append(Paragraph(f"+ {item['details']}", style_normal)) if item['satisfied'] == 1 else elements.append(Paragraph(f"- {item['details']}", style_normal))
            elements.append(Spacer(1, 10))

    render_section(remaped_reqs)

    doc.build(elements)

    # Merge with original PDF
    buffer.seek(0)
    new_pdf = PdfReader(buffer)
    existing_pdf = PdfReader(open(original_doc_papth, "rb"))

    output = PdfWriter()
    output.add_page(new_pdf.pages[0])
    for page in existing_pdf.pages:
        output.add_page(page)


    name_surname = original_doc_papth.split('\\')[1]
    filename = f'{name_surname.replace(' ','_')}'

    print(f"New path: {new_folder_path}\{filename}")

    with open(f"{new_folder_path}\{filename}", "wb") as f:
        output.write(f)

async def process_resume(cv_path, job_requirements):
    resume_pdf_text = extract_text_from_pdf(cv_path)
    text = resume_pdf_text 

    pattern = r"(Отклик на вакансию:|Желаемая должность и зарплата|Сопроводительное письмо|Опыт работы —|Образование|Навыки|Опыт вождения|Дополнительная информация|История общения с кандидатом)"
    resume_parts = re.split(pattern, text)

    # Convert to dict
    resume_dict = {}
    current_key = None

    for part in resume_parts:
        if part is None or part.strip() == "":
            continue
        if part.strip() in pattern:
            current_key = part.strip()
            current_key = section_map[current_key]
            resume_dict[current_key] = ""
        elif current_key:
            resume_dict[current_key] = part.strip()
    
    analyze_response_list = await anaylze_sections(job_requirements, resume_dict)

    analyze_results = [response.choices[0].message.tool_calls[0].function.arguments for response in analyze_response_list]

        # Parse JSON and extract arrays
    parsed = [json.loads(item)["requirements_satisfaction"] for item in analyze_results]

    # Apply element-wise binary OR
    binary_sum = reduce(lambda x, y: [a | b for a, b in zip(x, y)], parsed)

    id_mapped_requirements = map_requirements(job_requirements)

    for index, value in enumerate(binary_sum):
        requirement_id = index+1
        id_mapped_requirements[requirement_id]['satisfied'] = value
    
    new_create_analyzed_doc(id_mapped_requirements, cv_path, "checked_resumes_sasha")

