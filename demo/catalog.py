"""Demo master data for a Sailor (sailor.clothing) presentation.

Product names, list prices (BDT) and outlets were read from the public website and store
locator in November 2026. Where the site lists several designs under one name, a short
suffix tells them apart. Members are fictional: names are invented, mobile numbers use a
reserved-looking 01700-5550xx block and emails use example.com.
"""

COMPANY = "Sailor (Demo)"
ABBR = "SLR"
BRAND = "Sailor"
PROGRAM = "Sailor Club"
CUSTOMER_GROUP = "Sailor Members"
PRICE_LIST = "Sailor Retail"
ROOT_GROUP = "Sailor"

TIERS = [
    # tier, minimum lifetime spend, spend per point, card colour, benefits
    ("Blue", 0, 100, "#1d4ed8", "Welcome points and birthday bonus"),
    ("Silver", 20000, 80, "#64748b", "Faster earning and early access to sale"),
    ("Gold", 50000, 60, "#b45309", "Faster earning, free alteration and Gold-only rewards"),
    ("Platinum", 100000, 50, "#111827", "Top earning rate, private previews and priority service"),
]

# group -> [(code, name, price)]
ITEMS = {
    "Sailor Men": [
        ("SLR-M-101", "Mens Classic Panjabi", 3490),
        ("SLR-M-102", "Mens Classic Panjabi (Print)", 2790),
        ("SLR-M-103", "Mens Fashion Panjabi", 2990),
        ("SLR-M-111", "Mens Casual Shirt (F/S)", 2140),
        ("SLR-M-112", "Mens Casual Shirt (H/S)", 1790),
        ("SLR-M-113", "Mens Business Formal Shirt (F/S)", 2990),
        ("SLR-M-114", "Mens Fashion Express Shirt", 2790),
        ("SLR-M-121", "Mens Knit Basic Polo (H/S)", 1390),
        ("SLR-M-122", "Mens Knit Fashion Polo (H/S)", 1790),
        ("SLR-M-123", "Mens Knit Basic Polo", 1590),
        ("SLR-M-124", "Unisex Knit T-Shirt (H/S)", 550),
        ("SLR-M-131", "Mens Denim Trouser", 2590),
        ("SLR-M-132", "Mens Denim Trouser (Slim)", 2690),
        ("SLR-M-133", "Mens Chino Trouser", 2190),
        ("SLR-M-134", "Mens Chino Trouser (Regular)", 1990),
    ],
    "Sailor Women": [
        ("SLR-W-201", "Womens Woven Long Kurti", 2750),
        ("SLR-W-202", "Womens Woven Long Kurti (Embroidered)", 3250),
        ("SLR-W-203", "Womens Woven Long Kurti (Print)", 2100),
        ("SLR-W-211", "Womens Woven 3pcs", 7125),
        ("SLR-W-212", "Womens Woven 3pcs (Cotton)", 5650),
        ("SLR-W-213", "Womens Woven 3pcs (Premium)", 9250),
    ],
    "Sailor Kids": [
        ("SLR-K-301", "Boy's Fusion Panjabi", 1640),
        ("SLR-K-302", "Boy's Classic Panjabi", 1190),
        ("SLR-K-303", "Boy's Kabli Suit", 2240),
        ("SLR-K-304", "Boy's Premium Panjabi Set", 3090),
        ("SLR-K-311", "Girls Woven Party Dress", 3325),
    ],
    "Sailor Footwear": [
        ("SLR-F-401", "Womens Wedge Sandal", 3350),
        ("SLR-F-402", "Women's Block Heel Shoe", 2850),
        ("SLR-F-403", "Women's Block Heel Slide Sandal", 2650),
        ("SLR-F-404", "Womens Casual Ballerina Shoe", 3050),
        ("SLR-F-411", "Men's Fashion Sneaker", 4690),
        ("SLR-F-412", "Men's Casual Loafer (P)", 9900),
        ("SLR-F-421", "Girl's Fashion Sneaker", 1990),
    ],
    "Sailor Accessories": [
        ("SLR-A-501", "Mens Long Wallet", 1690),
        ("SLR-A-502", "Mens Wallet", 1490),
        ("SLR-A-503", "Mens Formal Belt", 2390),
        ("SLR-A-504", "Mens Baseball Cap", 550),
    ],
}

# name, code, division, city, phone, address, hours
STORES = [
    ("Sailor Bashundhara", "BSH", "Dhaka", "Dhaka", "01313433023", "Level 8, Block A, Bashundhara City Shopping Mall, Dhaka 1215", "10:00AM - 09:00PM, closed Tuesday"),
    ("Sailor Dhanmondi", "DHN", "Dhaka", "Dhaka", "01313433029", "House 742-743, Road 9/A, Dhanmondi", "10:00AM - 08:00PM, open 7 days"),
    ("Sailor Uttara", "UTT", "Dhaka", "Dhaka", "01777702003", "12 Sonargaon Janapath Road, Uttara", "10:00AM - 08:00PM, open 7 days"),
    ("Sailor Jamuna Future Park", "JFP", "Dhaka", "Dhaka", "01777702001", "North Court, Ground Floor, Progati Avenue", "11:00AM - 08:00PM, closed Wednesday"),
    ("Sailor Chattogram", "CTG", "Chattogram", "Chattogram", "01713656673", "Innovative Bhuiyan Orchid, Bayejid Bostami Road, East Nasirabad", "10:00AM - 10:00PM, open 7 days"),
    ("Sailor Sylhet", "SYL", "Sylhet", "Sylhet", "01313433032", "Aporupa Complex, Nayasarak, Sylhet", "10:00AM - 10:00PM, closed Friday"),
    ("Sailor Khulna", "KHL", "Khulna", "Khulna", "01321135024", "Plot A-56 and A-57, Majid Saroni Road", "10:00AM - 10:00PM, closed Friday"),
    ("Sailor Rajshahi", "RAJ", "Rajshahi", "Rajshahi", "01313433035", "ARC Ashirbad Tower, Gonok Para, Ranibazar, Boalia", "10:00AM - 10:00PM, closed Friday"),
]
# Share of members by home store (Dhaka outlets carry most of the traffic).
STORE_WEIGHTS = [20, 16, 12, 12, 14, 9, 9, 8]

MALE_NAMES = [
    "Arif", "Tanvir", "Rakib", "Imran", "Sajid", "Fahim", "Nayeem", "Shakil", "Mahmud", "Rifat", "Sabbir", "Tareq",
    "Zubair", "Asif", "Mehedi", "Rashed", "Kamrul", "Jubayer", "Shahriar", "Ashik", "Noman", "Tahsin", "Galib", "Adnan",
]
FEMALE_NAMES = [
    "Nusrat", "Farhana", "Tasnim", "Sadia", "Maliha", "Sumaiya", "Rumana", "Tahmina", "Anika", "Lamia", "Jannat",
    "Mahira", "Samira", "Nabila", "Afsana", "Raisa", "Tanjila", "Ishrat", "Fariha", "Sharmin", "Zarin", "Mithila",
    "Rifah", "Sabrina",
]
SURNAMES = [
    "Rahman", "Hossain", "Islam", "Ahmed", "Chowdhury", "Karim", "Khan", "Akter", "Sultana", "Haque", "Uddin", "Alam",
    "Siddique", "Mahmud", "Kabir", "Sarker", "Mia", "Talukder", "Bhuiyan", "Majumder",
]

REWARDS = [
    # name, type, points, voucher value, discount %, free item, minimum tier, description
    ("15% Off Next Purchase", "Discount Voucher", 300, 0, 15, None, None, "One-time 15% discount on your next bill"),
    ("Free Baseball Cap", "Free Item", 450, 0, 0, "SLR-A-504", None, "Mens Baseball Cap, any colour in stock"),
    ("Tk 500 Shopping Voucher", "Cash Voucher", 500, 500, 0, None, None, "Use against any purchase in store"),
    ("Tk 1,000 Shopping Voucher", "Cash Voucher", 900, 1000, 0, None, "Silver", "Silver members and above"),
    ("Tk 2,500 Festive Voucher", "Cash Voucher", 2000, 2500, 0, None, "Gold", "Gold and Platinum members only"),
]

SEGMENTS = [
    {"segment_name": "Gold and Platinum VIPs", "description": "Top two tiers, for previews and clienteling", "tiers": "Gold, Platinum"},
    {"segment_name": "Lapsed 60 Days", "description": "Bought before, nothing in the last 60 days", "not_purchased_in_days": 60},
    {"segment_name": "Birthday This Month", "description": "Members with a birthday in the current month", "birthday_month": "This Month"},
    {"segment_name": "Womenswear Buyers 90 Days", "description": "Bought from Women in the last 90 days", "item_group": "Sailor Women", "item_group_within_days": 90},
    {"segment_name": "New Members 30 Days", "description": "Joined in the last 30 days", "enrolled_within_days": 30},
    {"segment_name": "Dhaka High Spenders", "description": "Dhaka members with lifetime spend above Tk 30,000", "city": "Dhaka", "min_lifetime_spend": 30000},
    {"segment_name": "Points Ready to Redeem", "description": "500 points or more, reachable by SMS", "min_points_balance": 500, "require_sms_opt_in": 1},
]

CAMPAIGNS = [
    {
        "campaign_name": "Winter Collection Preview",
        "segment": "Gold and Platinum VIPs",
        "channel": "SMS and Email",
        "offer_code": "WINTER26",
        "sms_message": "Dear {{ first_name }}, as a {{ tier }} member you get first look at the Sailor Winter Collection this weekend. Show your card: {{ card_url }}",
        "email_subject": "{{ first_name }}, your private preview of the Winter Collection",
        "email_message": "<p>Dear {{ member_name }},</p><p>As a <b>{{ tier }}</b> member of Sailor Club you are invited to preview our Winter Collection before it reaches the floor. Quote <b>{{ offer_code }}</b> at the till.</p><p>You have <b>{{ points_balance }}</b> points to spend. Your card: <a href=\"{{ card_url }}\">{{ card_number }}</a></p>",
        "_send": True,
        "_window": (-30, -16),
    },
    {
        "campaign_name": "We Miss You: 200 Bonus Points",
        "segment": "Lapsed 60 Days",
        "channel": "SMS",
        "offer_code": "COMEBACK",
        "bonus_points": 200,
        "sms_message": "{{ first_name }}, we miss you at Sailor! We have added 200 bonus points to your card. You now have points worth using this week: {{ card_url }}",
    },
    {
        "campaign_name": "Birthday Treat",
        "segment": "Birthday This Month",
        "channel": "SMS",
        "offer_code": "BDAY15",
        "sms_message": "Happy birthday month, {{ first_name }}! Enjoy 15% off any one item at Sailor with code {{ offer_code }}. Your card: {{ card_url }}",
    },
]
