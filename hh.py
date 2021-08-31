import requests
import json
import time
import psycopg2
import db_setting # файл с настройками для БД
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import re

class Headhunter:
    def __init__(self, text = 'python junior', area = 113):
        self.text = text
        self.area = area
        
    def GetVacancysList(self):
       
        """
        Метод для полуяения списка ссылок на вакансии. \n
        Без аргументов.\n
        Внутри себя вызывает приватный метод __GetPage\n
        """
       
        self.url_list = []

        for page in range(20):
            js_str = self.__GetPage(page) #получаем ответ в виде json - файла
            js = json.loads(js_str) # Преобразуем текст ответа запроса в словарь Python
            # добавляем url в список ссылок
            self.url_list.extend([js['items'][i]['url'] for i in range(len(js['items']))])
            if (js['pages'] - page) <= 1:
                break
            time.sleep(0.5)
        return self.url_list

    def __GetPage(self, page = 0):
        """
        Функция для получения страницы со списком вакансий.\n
        Аргументы:\n
            page - Индекс страницы (число), начинается с 0. Значение по умолчанию 0, т.е. первая страница\n
        """
        # Словарь для параметров GET-запроса
        params = {
            'text': self.text,
            'page': page, # Индекс страницы поиска на HH
            'per_page': 100, # Кол-во вакансий на 1 странице
            'area': self.area 
        }
        
        req = requests.get('https://api.hh.ru/vacancies', params) # Посылаем запрос к API
        data = req.content.decode() # Декодируем его ответ, чтобы Кириллица отображалась корректно
        req.close()
        return data
            
        
    def GetVacancyDetail(self, url):
        """
        Метод для получения детальной информации о вакансии\n
        Аргументы:\n
            url - ссылка (строка) на вакансию в формате api (например: https://api.hh.ru/vacancies/44528998?host=hh.ru)\n
        """
        self.url = url
        req = requests.get(self.url)
        # with open('vacancy_detail.json', 'w', encoding='utf8') as f:
        #     f.write(req.content.decode())
        self.detail = json.loads(req.content.decode())
        req.close()
        time.sleep(0.3)
        return self.detail


class DatabaseWorker():
    def __init__(self):
        self.login = db_setting.LOGIN
        self.password = db_setting.PASSWORD
        self.host = db_setting.HOST
        self.port = db_setting.PORT
        self.database = db_setting.DB_NAME

    def SqlRequest(self, request):
        """
        Метод для работы с запросами к PostgreSQL.
        Аргументы:\n
            request - строка содержащая SQL-запрос\n
        Изначально реализовывал 2 метода отдельно для SELECT и INSERT.\n
        Но в таком случае не мог реализовать сложные SELECT'ы с JOIN'ами и тому подобным.\n
        В данной реализации в метод передается уже готовый запрос
        
        """
        try:
            # кортеж параметров для подключения к БД
            connection = psycopg2.connect(
                user = self.login,
                password = self.password,
                host = self.host,
                port = self.port,
                database = self.database
            )
            connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = connection.cursor()
            cursor.execute(request)
            if re.match(r'SELECT', request, re.IGNORECASE) is not None: # регулярка для поиска SELECT в начале строки
                return cursor.fetchall()
        except (Exception, psycopg2.Error) as error:
            print("Что-то пошло не так", error)
        finally:
            if connection:
                cursor.close()
                connection.close
# коректно работающие запросы в предыдущейверсии логики
    # INSERT INTO {table_name} ({columns}) VALUES ({', '.join(['%s'] * len(values))});
    # SELECT {col} FROM {t_name} WHERE {f_col} = $${f_val}$$;

vacancys = Headhunter()
db = DatabaseWorker()
for url in vacancys.GetVacancysList():
    # что бы не делать запрос к API каждый раз
    vacancy_detail_dict = vacancys.GetVacancyDetail(url)
    # проверяем наличие hh_id в локальной БД что бы не дергать базу одними и теми же вакансиями
    # и начинаем проверку других таблиц только если hh_id нет в базе
    select_hh_id = """SELECT hh_id FROM vacancy WHERE hh_id = $${vac}$$;""".format(vac = vacancy_detail_dict['id'])
    if len(db.SqlRequest(select_hh_id)) == 0:
        # запись ключевых навыков в БД
        skill_list = [skill['name'] for skill in vacancy_detail_dict['key_skills']]
        for skill in skill_list:
            select_keyskill = """SELECT name FROM keyskill WHERE name = $${req_skill}$$;""".format(req_skill=skill)
            if skill not in [skill[0] for skill in db.SqlRequest(select_keyskill)]:
                insert_keyskill = """INSERT INTO keyskill (name) VALUES ($${req_skill}$$);""".format(req_skill=skill)
                db.SqlRequest(insert_keyskill)
        
        # запись городов в БД
        city_name = vacancy_detail_dict['area']['name']
        select_city = """SELECT name FROM city WHERE name = $${req_city}$$""".format(req_city = city_name)
        if city_name not in [city[0] for city in db.SqlRequest(select_city)]:
            insert_city = """INSERT INTO city (name) VALUES ($${req_city}$$)""".format(req_city = city_name)
            db.SqlRequest(insert_city)

        # запись работодателей в БД
        employer_tuple = (vacancy_detail_dict['employer']['name'], vacancy_detail_dict['employer']['url'])
        select_employer = """SELECT name FROM employer WHERE name = $${req_employer}$$""".format(req_employer=vacancy_detail_dict['employer']['name'])
        if employer_tuple[0] not in [employer[0] for employer in db.SqlRequest(select_employer)]:
            insert_employer = """INSERT INTO employer (name, url) VALUES {req_employer}""".format(req_employer=employer_tuple)
            print(employer_tuple)
            # x.InsertToBase('employer', 'name, url', employer_tuple)
            db.SqlRequest(insert_employer)
        
#         # запись городов в БД
#         city_name = vacancy_detail_dict['area']['name']
#         if city_name not in [city[0] for city in x.SelectFromBase('name', 'city', 'name', city_name)]:
#             x.InsertToBase('city', 'name', (city_name,) )

#         # запись работодателей в БД
#         employer_tuple = (vacancy_detail_dict['employer']['name'], vacancy_detail_dict['employer']['url'])
#         if employer_tuple[0] not in [employer[0] for employer in x.SelectFromBase('name', 'employer', 'name', vacancy_detail_dict['employer']['name'])]:
#             x.InsertToBase('employer', 'name, url', employer_tuple)

#         # обработка пустых значений вознаграждения
#         if vacancy_detail_dict['salary'] is None:
#             salary_from = 0
#             salary_to = 0
#             salary_currency = 'n/n'
#         else:
#             salary_from = vacancy_detail_dict['salary']['from']

#             if vacancy_detail_dict['salary']['to'] is None:
#                 salary_to = 0
#             else:
#                 salary_to = vacancy_detail_dict['salary']['to']
#             salary_currency = vacancy_detail_dict['salary']['currency']
        
#         # кортеж с данными о вакансии
#         vacancy_detail_tuple = (
#             vacancy_detail_dict['id'], #строка
#             vacancy_detail_dict['name'],
#             salary_from,
#             salary_to,
#             salary_currency,
#             vacancy_detail_dict['description'],
#             vacancy_detail_dict['created_at'][:10],
#             [id[0] for id in x.SelectFromBase('id', 'city', 'name', vacancy_detail_dict['area']['name'])][0],
#             [id[0] for id in x.SelectFromBase('id', 'employer', 'name', vacancy_detail_dict['employer']['name'])][0]
#         )

#         # запись вакансии в БД
#         if int(vacancy_detail_tuple[0]) not in [vacancy_id[0] for vacancy_id in x.SelectFromBase('hh_id', 'vacancy', 'hh_id', vacancy_detail_tuple[0])]:
#             x.InsertToBase(
#                 'vacancy',
#                 'hh_id, name, salary_from, salary_to, salary_currency, description, date_create, city_id, employer_id',
#                 vacancy_detail_tuple
#                 )
        
#         # запись связующей таблицы vacancy_skill
#         vacancy_id = [id[0] for id in x.SelectFromBase('id', 'vacancy', 'hh_id', vacancy_detail_dict['id'])]
#         skill_id_list = [[id[0] for id in x.SelectFromBase('id', 'keyskill', 'name', skill)][0] for skill in skill_list]
#         vacancy_id_skill_id_pair = [(vac_id, s_id) for vac_id in vacancy_id for s_id in skill_id_list]
#         for pair in vacancy_id_skill_id_pair:
#             if pair not in [pair for pair in x.SelectFromBase('vacancy_id, keyskill_id', 'vacancy_skill', 'vacancy_id', vacancy_id[0])]:
#                 x.InsertToBase('vacancy_skill', 'vacancy_id, keyskill_id', pair)
    

# req = """SELect id, name FROM keyskill where name = 'Python'"""
# print(db.SqlRequest(req))

# select vacancy.name, keyskill.name, employer.name
# from 
#   vacancy 
# left join 
#   employer 
#       on vacancy.employer_id = employer.id
# left join
#   vacancy_skill
#       on vacancy.id = vacancy_skill.vacancy_id
# left join
#   keyskill
#       on vacancy_skill.keyskill_id = keyskill.id
# where
#   keyskill.name='Python';

# посчитать в скольких выкансиях встечается навык, например, Python
# select keyskill.name, count(*) 
# from keyskill 
# left join vacancy_skill on vacancy_skill.keyskill_id = keyskill.id
# where vacancy_skill.keyskill_id = (select id from keyskill where name='Python')
# group by keyskill.name;

# вывод ключевых навыков со счетчиком для каждого

# select keyskill.name, count(*)
# from keyskill
# left join vacancy_skill on vacancy_skill.keyskill_id = keyskill.id
# group by keyskill.name # группировка поимени навыка
# order by count desc # сортировка по возрастанию счетчика
# limit 25; # лимит в 25 строк
