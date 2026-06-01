from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))

CITY_TZ = {
    "moscow": "Europe/Moscow", "москва": "Europe/Moscow",
    "st petersburg": "Europe/Moscow", "спб": "Europe/Moscow", "санкт-петербург": "Europe/Moscow",
    "london": "Europe/London", "лондон": "Europe/London",
    "paris": "Europe/Paris", "париж": "Europe/Paris",
    "berlin": "Europe/Berlin", "берлин": "Europe/Berlin",
    "rome": "Europe/Rome", "рим": "Europe/Rome",
    "madrid": "Europe/Madrid", "мадрид": "Europe/Madrid",
    "barcelona": "Europe/Madrid", "барселона": "Europe/Madrid",
    "istanbul": "Europe/Istanbul", "стамбул": "Europe/Istanbul",
    "dubai": "Asia/Dubai", "дубай": "Asia/Dubai",
    "bangkok": "Asia/Bangkok", "банкок": "Asia/Bangkok", "бангкок": "Asia/Bangkok",
    "phuket": "Asia/Bangkok", "пхукет": "Asia/Bangkok",
    "pattaya": "Asia/Bangkok", "паттайя": "Asia/Bangkok",
    "tokyo": "Asia/Tokyo", "токио": "Asia/Tokyo", "токио": "Asia/Tokyo",
    "seoul": "Asia/Seoul", "сеул": "Asia/Seoul",
    "beijing": "Asia/Shanghai", "пекин": "Asia/Shanghai", "shanghai": "Asia/Shanghai", "шанхай": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong", "гонконг": "Asia/Hong_Kong",
    "singapore": "Asia/Singapore", "сингапур": "Asia/Singapore",
    "bali": "Asia/Makassar", "бали": "Asia/Makassar",
    "delhi": "Asia/Kolkata", "дели": "Asia/Kolkata", "mumbai": "Asia/Kolkata", "мумбаи": "Asia/Kolkata",
    "bangkok": "Asia/Bangkok",
    "new york": "America/New_York", "нью-йорк": "America/New_York", "нью йорк": "America/New_York",
    "chicago": "America/Chicago", "чикаго": "America/Chicago",
    "los angeles": "America/Los_Angeles", "ла": "America/Los_Angeles", "лос-анджелес": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles", "сан-франциско": "America/Los_Angeles",
    "toronto": "America/Toronto", "торонто": "America/Toronto",
    "mexico": "America/Mexico_City", "мексика": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo", "сан-паулу": "America/Sao_Paulo",
    "buenos aires": "America/Argentina/Buenos_Aires", "буэнос-айрес": "America/Argentina/Buenos_Aires",
    "sydney": "Australia/Sydney", "сидней": "Australia/Sydney",
    "melbourne": "Australia/Melbourne", "мельбурн": "Australia/Melbourne",
    "dubai": "Asia/Dubai",
    "doha": "Asia/Qatar", "доха": "Asia/Qatar",
    "tel aviv": "Asia/Jerusalem", "тель-авив": "Asia/Jerusalem",
    "cairo": "Africa/Cairo", "каир": "Africa/Cairo",
    "cape town": "Africa/Johannesburg", "кейптаун": "Africa/Johannesburg",
    "nairobi": "Africa/Nairobi", "найроби": "Africa/Nairobi",
    "kathmandu": "Asia/Kathmandu", "катманду": "Asia/Kathmandu",
    "hanoi": "Asia/Bangkok", "ханой": "Asia/Bangkok",
    "ho chi minh": "Asia/Ho_Chi_Minh", "хошимин": "Asia/Ho_Chi_Minh",
    "kuala lumpur": "Asia/Kuala_Lumpur", "куала-лумпур": "Asia/Kuala_Lumpur",
    "manila": "Asia/Manila", "манила": "Asia/Manila",
    "jakarta": "Asia/Jakarta", "джакарта": "Asia/Jakarta",
    "colombo": "Asia/Colombo", "коломбо": "Asia/Colombo",
    "dhaka": "Asia/Dhaka", "дакка": "Asia/Dhaka",
    "karachi": "Asia/Karachi", "карачи": "Asia/Karachi",
    "tehran": "Asia/Tehran", "тегеран": "Asia/Tehran",
    "tbilisi": "Asia/Tbilisi", "тбилиси": "Asia/Tbilisi",
    "yerevan": "Asia/Yerevan", "ереван": "Asia/Yerevan",
    "baku": "Asia/Baku", "баку": "Asia/Baku",
    "astana": "Asia/Almaty", "астана": "Asia/Almaty", "almaty": "Asia/Almaty", "алматы": "Asia/Almaty",
    "tashkent": "Asia/Tashkent", "ташкент": "Asia/Tashkent",
    "minsk": "Europe/Minsk", "минск": "Europe/Minsk",
    "kiev": "Europe/Kiev", "киев": "Europe/Kiev", "kyiv": "Europe/Kiev",
    "warsaw": "Europe/Warsaw", "варшава": "Europe/Warsaw",
    "prague": "Europe/Prague", "прага": "Europe/Prague",
    "vienna": "Europe/Vienna", "вена": "Europe/Vienna",
    "budapest": "Europe/Budapest", "будапешт": "Europe/Budapest",
    "athens": "Europe/Athens", "афины": "Europe/Athens",
    "copenhagen": "Europe/Copenhagen", "копенгаген": "Europe/Copenhagen",
    "stockholm": "Europe/Stockholm", "стокгольм": "Europe/Stockholm",
    "oslo": "Europe/Oslo", "осло": "Europe/Oslo",
    "helsinki": "Europe/Helsinki", "хельсинки": "Europe/Helsinki",
    "reykjavik": "Africa/Abidjan", "рейкьявик": "Africa/Abidjan",
    "lisbon": "Europe/Lisbon", "лиссабон": "Europe/Lisbon",
    "amsterdam": "Europe/Amsterdam", "амстердам": "Europe/Amsterdam",
    "brussels": "Europe/Brussels", "брюссель": "Europe/Brussels",
    "zurich": "Europe/Zurich", "цюрих": "Europe/Zurich",
    "milan": "Europe/Rome", "милан": "Europe/Rome",
    "bali": "Asia/Makassar",
    "saigon": "Asia/Ho_Chi_Minh",
    "chiang mai": "Asia/Bangkok", "чиангмай": "Asia/Bangkok",
    "goa": "Asia/Kolkata", "гоа": "Asia/Kolkata",
    "vladivostok": "Asia/Vladivostok", "владивосток": "Asia/Vladivostok",
    "novosibirsk": "Asia/Novosibirsk", "новосибирск": "Asia/Novosibirsk",
    "ekaterinburg": "Asia/Yekaterinburg", "екатеринбург": "Asia/Yekaterinburg",
    "kazan": "Europe/Moscow", "казань": "Europe/Moscow",
    "sochi": "Europe/Moscow", "сочи": "Europe/Moscow",
    "krasnodar": "Europe/Moscow", "краснодар": "Europe/Moscow",
    "rostov": "Europe/Moscow", "ростов": "Europe/Moscow",
    "samara": "Europe/Samara", "самара": "Europe/Samara",
    "nizhny novgorod": "Europe/Moscow", "нижний новгород": "Europe/Moscow",
    "chelyabinsk": "Asia/Yekaterinburg", "челябинск": "Asia/Yekaterinburg",
    "omsk": "Asia/Omsk", "омск": "Asia/Omsk",
    "krasnoyarsk": "Asia/Krasnoyarsk", "красноярск": "Asia/Krasnoyarsk",
    "irkutsk": "Asia/Irkutsk", "иркутск": "Asia/Irkutsk",
    "khabarovsk": "Asia/Vladivostok", "хабаровск": "Asia/Vladivostok",
    "kaliningrad": "Europe/Kaliningrad", "калининград": "Europe/Kaliningrad",
}

COUNTRY_TZ = {
    "russia": "Europe/Moscow", "россия": "Europe/Moscow", "russian federation": "Europe/Moscow",
    "thailand": "Asia/Bangkok", "таиланд": "Asia/Bangkok", "тайланд": "Asia/Bangkok",
    "turkey": "Europe/Istanbul", "турция": "Europe/Istanbul", "туркей": "Europe/Istanbul",
    "uae": "Asia/Dubai", "оаэ": "Asia/Dubai", "объединенные арабские эмираты": "Asia/Dubai",
    "india": "Asia/Kolkata", "индия": "Asia/Kolkata",
    "china": "Asia/Shanghai", "китай": "Asia/Shanghai", "kитай": "Asia/Shanghai",
    "vietnam": "Asia/Bangkok", "вьетнам": "Asia/Bangkok",
    "indonesia": "Asia/Jakarta", "индонезия": "Asia/Jakarta",
    "usa": "America/New_York", "сша": "America/New_York", "america": "America/New_York",
    "uk": "Europe/London", "великобритания": "Europe/London", "britain": "Europe/London",
    "germany": "Europe/Berlin", "германия": "Europe/Berlin",
    "france": "Europe/Paris", "франция": "Europe/Paris",
    "spain": "Europe/Madrid", "испания": "Europe/Madrid",
    "italy": "Europe/Rome", "италия": "Europe/Rome",
    "japan": "Asia/Tokyo", "япония": "Asia/Tokyo",
    "south korea": "Asia/Seoul", "южная корея": "Asia/Seoul",
    "australia": "Australia/Sydney", "австралия": "Australia/Sydney",
    "brazil": "America/Sao_Paulo", "бразилия": "America/Sao_Paulo",
    "egypt": "Africa/Cairo", "египет": "Africa/Cairo",
    "kazakhstan": "Asia/Almaty", "казахстан": "Asia/Almaty",
    "belarus": "Europe/Minsk", "беларусь": "Europe/Minsk", "белоруссия": "Europe/Minsk",
    "ukraine": "Europe/Kiev", "украина": "Europe/Kiev",
    "georgia": "Asia/Tbilisi", "грузия": "Asia/Tbilisi",
    "armenia": "Asia/Yerevan", "армения": "Asia/Yerevan",
    "azerbaijan": "Asia/Baku", "азербайджан": "Asia/Baku",
    "uzbekistan": "Asia/Tashkent", "узбекистан": "Asia/Tashkent",
    "thailand": "Asia/Bangkok",
    "vietnam": "Asia/Ho_Chi_Minh",
    "cambodia": "Asia/Phnom_Penh", "камбоджа": "Asia/Phnom_Penh",
    "laos": "Asia/Bangkok", "лаос": "Asia/Bangkok",
    "myanmar": "Asia/Yangon", "мьянма": "Asia/Yangon",
    "nepal": "Asia/Kathmandu", "непал": "Asia/Kathmandu",
    "sri lanka": "Asia/Colombo", "шри-ланка": "Asia/Colombo",
    "malaysia": "Asia/Kuala_Lumpur", "малайзия": "Asia/Kuala_Lumpur",
    "philippines": "Asia/Manila", "филиппины": "Asia/Manila",
    "portugal": "Europe/Lisbon", "португалия": "Europe/Lisbon",
    "netherlands": "Europe/Amsterdam", "нидерланды": "Europe/Amsterdam", "голландия": "Europe/Amsterdam",
    "switzerland": "Europe/Zurich", "швейцария": "Europe/Zurich",
    "austria": "Europe/Vienna", "австрия": "Europe/Vienna",
    "poland": "Europe/Warsaw", "польша": "Europe/Warsaw",
    "czech": "Europe/Prague", "чехия": "Europe/Prague",
    "hungary": "Europe/Budapest", "венгрия": "Europe/Budapest",
    "greece": "Europe/Athens", "греция": "Europe/Athens",
    "bulgaria": "Europe/Sofia", "болгария": "Europe/Sofia",
    "romania": "Europe/Bucharest", "румыния": "Europe/Bucharest",
    "serbia": "Europe/Belgrade", "сербия": "Europe/Belgrade",
    "croatia": "Europe/Zagreb", "хорватия": "Europe/Zagreb",
    "montenegro": "Europe/Podgorica", "черногория": "Europe/Podgorica",
    "israel": "Asia/Jerusalem", "израиль": "Asia/Jerusalem",
    "qatar": "Asia/Qatar", "катар": "Asia/Qatar",
}


def find_timezone(location: str) -> str | None:
    key = location.strip().lower()
    if key in CITY_TZ:
        return CITY_TZ[key]
    if key in COUNTRY_TZ:
        return COUNTRY_TZ[key]
    return None


def format_dual_time(dt: datetime | None = None, user_tz: str | None = None, fmt: str = "%H:%M") -> str:
    if dt is None:
        dt = datetime.now(timezone.utc)
    msk_time = dt.astimezone(MSK).strftime(fmt)
    if user_tz and user_tz != "UTC":
        try:
            import zoneinfo
            local = dt.astimezone(zoneinfo.ZoneInfo(user_tz))
            local_str = local.strftime(fmt)
            if local.utcoffset() != MSK.utcoffset(dt):
                return f"{msk_time} MSK / {local_str} local"
        except Exception:
            pass
    return f"{msk_time} MSK"
