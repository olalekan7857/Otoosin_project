"""Initial legal page content, migrated from the public policy templates.

Edit this content from the Legal & Policies admin page. Body text is plain
text: separate paragraphs with a blank line and start list items with "- ".
"""

DEFAULT_LEGAL_DOCUMENTS = {'privacy': {'slug': 'privacy',
             'title': 'Privacy Policy',
             'eyebrow': 'Your information',
             'intro': 'This policy explains how O’TOOSIN Farms handles personal '
                      'information connected with this website, its product pages and '
                      'its ordering process.',
             'lead': 'O’TOOSIN Farms offers meats, fish, live animals, eggs, veggies '
                     'and fruits. This policy describes the information the website '
                     'can collect and the purposes it serves. It applies to this '
                     'website and not to other websites or services.',
             'sections': [{'anchor': 'scope',
                           'title': 'Scope of this policy',
                           'content': 'This Privacy Policy covers your use of the '
                                      'O’TOOSIN Farms website, including browsing '
                                      'product pages, using the cart and preparing an '
                                      'order at checkout.\n'
                                      '\n'
                                      'It does not cover information you give to a '
                                      'separate service that O’TOOSIN Farms does not '
                                      'control. Where this policy refers to '
                                      'information being used to fulfil an order, that '
                                      'includes arrangements made by O’TOOSIN Farms '
                                      'staff and the rider who delivers the order.',
                           'is_callout': False},
                          {'anchor': 'information-provided',
                           'title': 'Information you may provide',
                           'content': 'The information requested depends on how you '
                                      'use the website:\n'
                                      '- **Contact enquiries:** your full name, email '
                                      'address, an optional phone number, the type of '
                                      'enquiry and the message you write.\n'
                                      '- **Checkout details:** your name, phone '
                                      'number, optional email address, delivery '
                                      'address, city or town, state, an optional '
                                      'nearest landmark and optional delivery '
                                      'instructions.\n'
                                      '- **Order details:** the products you select, '
                                      'their Fresh, Frozen or Fried condition where '
                                      'applicable, the selling unit, the quantity and '
                                      'the totals shown during checkout.\n'
                                      '- **Correspondence:** any other details you '
                                      'choose to include when you contact O’TOOSIN '
                                      'Farms about a product, an existing order or a '
                                      'delivery.\n'
                                      '\n'
                                      'When you submit the Contact page form, a valid '
                                      'enquiry is stored in the O’Toosin Farms staff '
                                      'inbox so the team can review and respond to it. '
                                      'We do not send an automatic email notification '
                                      'for contact enquiries in this phase. Please '
                                      'include only the information needed to help '
                                      'with your enquiry.',
                           'is_callout': False},
                          {'anchor': 'automatic-information',
                           'title': 'Information collected automatically',
                           'content': 'This website does not run advertising networks, '
                                      'analytics products or tracking pixels. It does '
                                      'not create customer accounts and does not ask '
                                      'you to sign in.\n'
                                      '\n'
                                      'The site stores some information in your own '
                                      'browser so that it can work between pages: your '
                                      'cart, your product-view preference, your light '
                                      'or dark theme choice and a temporary copy of '
                                      'order details used by the confirmation page '
                                      'where that flow is used. This browser storage '
                                      'is described further in section 9.\n'
                                      '\n'
                                      'As with most websites, the providers that host '
                                      'the site or deliver its fonts may process '
                                      'standard technical request information, such as '
                                      'the address your device uses to connect and the '
                                      'type of browser making the request, in order to '
                                      'deliver the page. O’TOOSIN Farms does not use '
                                      'that information to build advertising profiles.',
                           'is_callout': False},
                          {'anchor': 'how-we-use',
                           'title': 'How information is used',
                           'content': 'Information you provide is used for the '
                                      'practical purposes connected with your '
                                      'request:\n'
                                      '- Reviewing and responding to an enquiry.\n'
                                      '- Preparing, confirming and arranging an '
                                      'order.\n'
                                      '- Coordinating delivery with you and the '
                                      'rider.\n'
                                      '- Communicating about a product, an order, a '
                                      'payment or delivery arrangement.\n'
                                      '- Keeping the records reasonably needed to run '
                                      'the business and deal with questions or '
                                      'complaints.\n'
                                      '- Meeting legal or regulatory obligations that '
                                      'apply to the business.\n'
                                      '\n'
                                      'O’TOOSIN Farms does not sell customer '
                                      'information, and does not use contact details '
                                      'for unrelated marketing without a lawful basis.',
                           'is_callout': False},
                          {'anchor': 'payments',
                           'title': 'Payments',
                           'content': 'This website handles payment as part of '
                                      'checkout. The checkout total includes the '
                                      'selected products and any applicable delivery '
                                      'fee, and you are not asked to arrange payment '
                                      'separately.\n'
                                      '\n'
                                      'Please do not send card details by email or '
                                      'chat. The website does not store full '
                                      'payment-card information. An order summary is '
                                      'not a payment receipt and does not by itself '
                                      'show that a payment has been completed.\n'
                                      '\n'
                                      'Where a delivery fee applies, it is shown in '
                                      'the order summary. For park delivery, the '
                                      'delivery charge is confirmed before dispatch. '
                                      'Pickup has no delivery fee.',
                           'is_callout': False},
                          {'anchor': 'sharing',
                           'title': 'Sharing information',
                           'content': 'Information is shared only where it is needed '
                                      'for the purpose for which it was provided. This '
                                      'can include:\n'
                                      '- **Delivery riders and couriers:** the name, '
                                      'phone number, delivery address and delivery '
                                      'instructions needed to deliver an order.\n'
                                      '- **Service providers:** providers that host, '
                                      'secure or maintain the website or its fonts, '
                                      'where their involvement is necessary to make '
                                      'the site available.\n'
                                      '- **Legal or regulatory disclosures:** where '
                                      'disclosure is required by law or is reasonably '
                                      'necessary to establish, exercise or defend a '
                                      'legal claim.\n'
                                      '\n'
                                      'O’TOOSIN Farms does not share information with '
                                      'advertisers, data brokers or unrelated third '
                                      'parties for their own marketing.',
                           'is_callout': False},
                          {'anchor': 'retention',
                           'title': 'Data retention',
                           'content': 'Information is kept only for as long as it is '
                                      'reasonably needed for the purpose it was '
                                      'collected for, to handle an order or enquiry, '
                                      'to resolve a complaint, or to meet a legal or '
                                      'accounting requirement. Retention periods '
                                      'depend on the type of record and the '
                                      'circumstances; a single fixed period is not '
                                      'applied to every record.\n'
                                      '\n'
                                      'Information held only in your browser storage '
                                      'remains there until you clear it, until the '
                                      'relevant browser session ends, or until the '
                                      'website replaces it. O’TOOSIN Farms cannot '
                                      'delete information that exists only on your '
                                      'device.',
                           'is_callout': False},
                          {'anchor': 'security',
                           'title': 'Security',
                           'content': 'O’TOOSIN Farms aims to handle personal '
                                      'information carefully and to use reasonable '
                                      'measures to protect it against unauthorised '
                                      'access, loss or misuse. Measures are '
                                      'appropriate to the kind of information involved '
                                      'and the way it is held.\n'
                                      '\n'
                                      'No website transmission or storage method is '
                                      'completely secure, and absolute security cannot '
                                      'be guaranteed. If you have reason to believe '
                                      'information you provided has been mishandled, '
                                      'please raise it using the contact route below.',
                           'is_callout': False},
                          {'anchor': 'cookies',
                           'title': 'Cookies and browser storage',
                           'content': 'This website does not set advertising or '
                                      'analytics cookies. It uses browser storage for '
                                      'necessary functionality:\n'
                                      '- **Your cart:** saved in local storage so the '
                                      'items you add remain available as you move '
                                      'between pages.\n'
                                      '- **Display preferences:** your light or dark '
                                      'theme and your product-view preference may be '
                                      'saved in browser storage.\n'
                                      '- **Order review:** where the '
                                      'order-confirmation flow is used, a temporary '
                                      'copy of the order details may be kept in '
                                      'session storage for that browser session.\n'
                                      '\n'
                                      'You can clear this storage through your browser '
                                      'settings. Clearing it may remove your cart or '
                                      'reset your display preferences. The website '
                                      'also requests fonts from Google Fonts, which '
                                      "involves a request to Google's servers when the "
                                      'page loads.',
                           'is_callout': False},
                          {'anchor': 'rights',
                           'title': 'Your privacy rights',
                           'content': 'Depending on the law that applies to you, '
                                      'including the Nigeria Data Protection Act 2023 '
                                      'where it applies, you may have rights in '
                                      'relation to personal information about you. '
                                      'These can include the right to be informed '
                                      'about how your information is used, to request '
                                      'access to it, to ask for inaccurate information '
                                      'to be corrected, to request deletion in '
                                      'appropriate circumstances, to object to certain '
                                      'uses and to withdraw consent where consent is '
                                      'the basis for processing.\n'
                                      '\n'
                                      'To make a request or raise a privacy concern, '
                                      'use a verified O’TOOSIN Farms contact route '
                                      'where one is available and describe what you '
                                      'need. Please provide enough information for the '
                                      'request to be understood, but do not send '
                                      'sensitive information that is not needed. '
                                      'Requests are handled in accordance with '
                                      'applicable law; the website does not provide '
                                      'automated account controls or self-service '
                                      'deletion tools.\n'
                                      '\n'
                                      'You may also have the right to complain to the '
                                      'Nigeria Data Protection Commission. This policy '
                                      'does not claim that any particular '
                                      'certification, registration or compliance '
                                      'approval has been obtained.',
                           'is_callout': False},
                          {'anchor': 'children',
                           'title': "Children's privacy",
                           'content': 'O’TOOSIN Farms intends this website for adults '
                                      'placing household orders. The business does not '
                                      'knowingly collect personal information from '
                                      'children. If you believe a child has provided '
                                      'information through the website, please raise '
                                      'it using the contact route below so it can be '
                                      'reviewed.',
                           'is_callout': False},
                          {'anchor': 'changes',
                           'title': 'Policy updates',
                           'content': 'This policy may be updated when the website, '
                                      'the ordering process or the way customer '
                                      'information is handled changes. The current '
                                      'version is the one published on this page. '
                                      'Material changes will be reflected here, and '
                                      'you should review this page if you want to '
                                      'understand the current practices.',
                           'is_callout': False},
                          {'anchor': 'contact',
                           'title': 'Contact',
                           'content': 'Use the Contact page to ask about this policy '
                                      'or to request access, correction or deletion of '
                                      'personal information. Submitted enquiries are '
                                      'stored for staff review in the admin inbox. '
                                      'Please include only the information needed for '
                                      'your request.\n'
                                      '\n'
                                      '[Contact O’TOOSIN Farms](/contact/)',
                           'is_callout': True}]},
 'terms': {'slug': 'terms',
           'title': 'Terms & Conditions',
           'eyebrow': 'Using the store',
           'intro': 'These terms explain how the O’TOOSIN Farms website may be used, '
                    'how orders are prepared and confirmed, and how delivery, pickup '
                    'and payment are handled.',
           'lead': 'O’TOOSIN Farms offers meats, fish, live animals, eggs, veggies and '
                   'fruits through this website. By using the website, you agree to '
                   'the terms below. If you do not agree with them, please do not use '
                   'the website to prepare an order.',
           'sections': [{'anchor': 'acceptance',
                         'title': 'About these terms',
                         'content': 'These Terms & Conditions apply to your use of the '
                                    'O’TOOSIN Farms website and to orders prepared '
                                    'through it. They should be read together with the '
                                    '[Privacy Policy](/privacy/), which explains how '
                                    'personal information is handled.\n'
                                    '\n'
                                    'The website is a single-seller storefront: '
                                    'O’TOOSIN Farms sells directly to customers. It is '
                                    'not a marketplace and does not host other '
                                    'sellers.',
                         'is_callout': False},
                        {'anchor': 'website-use',
                         'title': 'Website use',
                         'content': 'You may use the website to browse products, read '
                                    'product details, add items to a cart, prepare an '
                                    'order and contact O’TOOSIN Farms about a product, '
                                    'order or delivery. You agree to use the website '
                                    'lawfully and not to:\n'
                                    '- Submit false, misleading or impersonating '
                                    'information.\n'
                                    '- Attempt to disrupt, overload, probe or gain '
                                    'unauthorised access to the website or its '
                                    'systems.\n'
                                    '- Use automated means to scrape or copy the '
                                    'website in a way that interferes with its normal '
                                    'operation.\n'
                                    '- Use the website or its content for unlawful '
                                    'purposes.',
                         'is_callout': False},
                        {'anchor': 'product-information',
                         'title': 'Product information',
                         'content': 'Product pages show the item, its category, its '
                                    'available condition or selling unit, its price '
                                    'and other details intended to help you choose. '
                                    'Please review the product name, unit, condition, '
                                    'price and quantity before preparing an order.\n'
                                    '\n'
                                    'Photographs are illustrative. The cut, trimming, '
                                    'packaging, size and exact appearance of a '
                                    'delivered item can vary from the photograph. '
                                    'Product availability can change, and an item '
                                    'displayed on the website is not a guarantee that '
                                    'it remains available until the order is '
                                    'confirmed.\n'
                                    '\n'
                                    'Nothing on this website is a claim of organic '
                                    'certification, farming-method certification or a '
                                    'guarantee of a particular result from a product.',
                         'is_callout': False},
                        {'anchor': 'categories',
                         'title': 'Product categories and conditions',
                         'content': 'The shop covers **Meats**, **Fish**, **Live '
                                    'Animals**, **Eggs**, **Veggies** and **Fruits**. '
                                    'Within Meats, the range includes pork, chicken, '
                                    'turkey, beef and goat meat. Pork, beef and goat '
                                    'meat are red meat; chicken and turkey are '
                                    'poultry; fish is seafood.\n'
                                    '\n'
                                    'Where a product-condition filter applies, the '
                                    'available conditions are **Fresh**, **Frozen** '
                                    'and **Fried**. These describe the state of a '
                                    'product, not a separate product category. '
                                    'Available conditions can differ by product.',
                         'is_callout': False},
                        {'anchor': 'pricing',
                         'title': 'Pricing and quantities',
                         'content': 'Product prices are displayed in Nigerian Naira '
                                    'for the selling unit shown on the item, such as '
                                    'per kilogram, per piece, per crate or per basket. '
                                    'When you enter a quantity, it represents the '
                                    'number of those units you want. The cart and '
                                    'checkout calculate the product subtotal from the '
                                    'selected price and quantity.\n'
                                    '\n'
                                    'The product subtotal shown at checkout covers the '
                                    'products only. Any applicable delivery fee is '
                                    'shown separately in the order summary and '
                                    'included in the order total. Pickup has no '
                                    'delivery fee. Prices and availability may change '
                                    'before an order is confirmed; the amount shown '
                                    'for your selection before you complete the '
                                    'ordering process is the amount that applies to '
                                    'that order.\n'
                                    '\n'
                                    'No minimum purchase quantity, fixed weight step '
                                    'or additional product fee applies unless it is '
                                    'expressly shown on the website.',
                         'is_callout': False},
                        {'anchor': 'orders',
                         'title': 'Orders and acceptance',
                         'content': 'Guest checkout is available; you do not need to '
                                    'create an account. The checkout lets you enter '
                                    'your contact and delivery details, choose '
                                    'delivery or pickup, and review your selection '
                                    'before finishing.\n'
                                    '\n'
                                    'An order becomes confirmed only when O’TOOSIN '
                                    'Farms accepts it and communicates that '
                                    'confirmation, and a payment is only treated as '
                                    'complete when it has been successfully processed '
                                    'through the checkout. If an item is unavailable '
                                    'or a detail needs clarification, the business may '
                                    'contact you before preparing the order.\n'
                                    '\n'
                                    'Please provide accurate information so the order '
                                    'can be reviewed and arranged without avoidable '
                                    'delay.',
                         'is_callout': False},
                        {'anchor': 'payment',
                         'title': 'Payment',
                         'content': 'Payment for products and any delivery charge is '
                                    'completed through the website at checkout. The '
                                    'total shown for the selected products and '
                                    'applicable delivery fee is the amount due for '
                                    'that order.\n'
                                    '\n'
                                    'Please do not send card details by email or chat. '
                                    'A payment is not treated as complete unless it '
                                    'has been successfully processed through the '
                                    'checkout.\n'
                                    '\n'
                                    'Any applicable delivery fee is displayed in the '
                                    'order summary and included in the order total. '
                                    'Pickup orders have no delivery fee.',
                         'is_callout': False},
                        {'anchor': 'delivery',
                         'title': 'Delivery, pickup and fees',
                         'content': 'Choose delivery to a supported location or '
                                    'collect your order from a pickup location at '
                                    'checkout. Delivery and pickup are arranged by '
                                    'O’TOOSIN Farms staff after an order is accepted. '
                                    'Please provide a complete address, the relevant '
                                    'city or town and state, and any landmark or '
                                    'instruction that will help the rider.\n'
                                    '\n'
                                    'For doorstep delivery within the listed Abeokuta '
                                    'zones, the applicable delivery fee is shown in '
                                    'the order summary and included in the order '
                                    'total. For park delivery, the approved '
                                    'destination and applicable delivery charge are '
                                    'also included in the checkout total. Pickup from '
                                    'Mummy-D Stores has no delivery fee.\n'
                                    '\n'
                                    'Delivery coverage, timing and any same-day '
                                    'arrangement are not guaranteed by these terms. '
                                    'They are confirmed as part of the order '
                                    'arrangement. If a delivery cannot be completed '
                                    'because the information provided is incomplete or '
                                    'nobody is available to receive the order, '
                                    'O’TOOSIN Farms or the rider will try to contact '
                                    'you to resolve it.',
                         'is_callout': False},
                        {'anchor': 'returns',
                         'title': 'Cancellations, returns, refunds and complaints',
                         'content': 'If you need to change or cancel an order, contact '
                                    'O’TOOSIN Farms as soon as possible using a '
                                    'verified contact route where one is available. '
                                    'Whether a change or cancellation is possible '
                                    'depends on whether the order has been confirmed, '
                                    'prepared or handed to a rider.\n'
                                    '\n'
                                    'Meat is a perishable product, so please inspect '
                                    'your order when it arrives and raise any problem '
                                    'promptly. If something is incorrect, damaged or '
                                    'not what you ordered, contact O’TOOSIN Farms with '
                                    'the order details so the matter can be reviewed.\n'
                                    '\n'
                                    'These terms do not set a fixed cancellation '
                                    'window, return period or refund timeline, and '
                                    'they do not create an automatic refund '
                                    'entitlement. Requests are considered individually '
                                    'in light of the circumstances and applicable law. '
                                    'Nothing in these terms is intended to exclude or '
                                    'limit rights that cannot lawfully be excluded.',
                         'is_callout': False},
                        {'anchor': 'responsibilities',
                         'title': 'Customer responsibilities',
                         'content': 'When using the website or ordering, you are '
                                    'responsible for:\n'
                                    '- Providing accurate contact, delivery and order '
                                    'information.\n'
                                    '- Reviewing the selected meat, condition, '
                                    'quantity and total before completing the order.\n'
                                    '- Providing clear delivery instructions and '
                                    'remaining reasonably reachable while delivery is '
                                    'arranged.\n'
                                    '- Reviewing the delivery or pickup choice and any '
                                    'charge shown, and completing payment through the '
                                    'website at checkout.\n'
                                    '- Using the website lawfully and respecting its '
                                    'content and operation.',
                         'is_callout': False},
                        {'anchor': 'availability',
                         'title': 'Website availability and errors',
                         'content': 'O’TOOSIN Farms aims to keep the website available '
                                    'and accurate, but access may be interrupted by '
                                    'maintenance, technical problems or circumstances '
                                    "outside the business's control. The website may "
                                    'contain errors in product information, pricing or '
                                    'availability. Reasonable steps will be taken to '
                                    'correct genuine errors, and an order affected by '
                                    'a manifest error may be reviewed with you before '
                                    'it is prepared.',
                         'is_callout': False},
                        {'anchor': 'ip',
                         'title': 'Intellectual property',
                         'content': 'The O’TOOSIN Farms name, logo, website text, '
                                    'layout, graphics and other original content are '
                                    'owned by or used for the business and are '
                                    'protected by applicable intellectual-property '
                                    'law. You may view and use the website for '
                                    'ordinary shopping and enquiry purposes. You may '
                                    'not reproduce, republish or commercially exploit '
                                    'the content without permission. Third-party '
                                    'assets remain the property of their respective '
                                    'owners.',
                         'is_callout': False},
                        {'anchor': 'third-parties',
                         'title': 'Third-party services',
                         'content': 'The website uses external font delivery to '
                                    'display its typography. Links to other websites, '
                                    'if present, are provided for convenience and are '
                                    "not under O’TOOSIN Farms' control.",
                         'is_callout': False},
                        {'anchor': 'privacy',
                         'title': 'Privacy',
                         'content': 'How personal information is collected and used is '
                                    'described in the [Privacy Policy](/privacy/). It '
                                    'forms part of the terms on which the website is '
                                    'made available.',
                         'is_callout': False},
                        {'anchor': 'changes',
                         'title': 'Changes to these terms',
                         'content': 'These terms may be updated when the website, '
                                    'ordering process or delivery arrangements change. '
                                    'The version published on this page is the current '
                                    'version. Please review it before placing a new '
                                    'order. Changes do not retrospectively alter an '
                                    'order that has already been confirmed, except '
                                    'where the law requires otherwise.',
                         'is_callout': False},
                        {'anchor': 'law',
                         'title': 'Applicable law and disputes',
                         'content': 'These terms are governed by the laws of the '
                                    'Federal Republic of Nigeria. If a concern arises, '
                                    'please contact O’TOOSIN Farms first so that it '
                                    'can be reviewed and, where possible, resolved '
                                    'directly. If a dispute cannot be resolved that '
                                    'way, it may be brought before a court or other '
                                    'body with jurisdiction over the matter.',
                         'is_callout': False},
                        {'anchor': 'contact',
                         'title': 'Contact',
                         'content': 'This website does not publish a separate email '
                                    'address or phone number for questions about these '
                                    'terms, a product, an existing order or a delivery '
                                    'arrangement, and the form on the Contact page '
                                    'does not itself transmit a message. Where a '
                                    'verified contact route is shown on that page, use '
                                    'it for your enquiry.\n'
                                    '\n'
                                    '[Contact O’TOOSIN Farms](/contact/)',
                         'is_callout': True}]}}
