from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.catalogue.models import Category, Course, Tag
from apps.accounts.models import Organization
from decimal import Decimal

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed the database with sample data'

    def handle(self, *args, **options):
        self.stdout.write('Seeding database...')
        
        # Create Categories
        categories_data = [
            ('Web Development', 'web-development', 'Learn to build modern websites and web applications'),
            ('Data Science', 'data-science', 'Master data analysis, visualization, and machine learning'),
            ('Cybersecurity', 'cybersecurity', 'Learn to protect systems and networks from threats'),
            ('Business', 'business', 'Develop business skills and strategies'),
            ('Design', 'design', 'Learn UI/UX design and graphic design'),
            ('Marketing', 'marketing', 'Master digital marketing and SEO'),
            ('Cloud Computing', 'cloud-computing', 'Learn AWS, Azure, and cloud architecture'),
            ('Mobile Development', 'mobile-development', 'Build iOS and Android applications'),
        ]
        
        categories = []
        for name, slug, desc in categories_data:
            cat, created = Category.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'description': desc, 'is_active': True}
            )
            categories.append(cat)
            if created:
                self.stdout.write(f'  Created category: {name}')
        
        # Create Tags
        tags_data = ['Python', 'JavaScript', 'React', 'Django', 'AWS', 'Docker', 'Kubernetes', 'Machine Learning']
        tags = []
        for tag_name in tags_data:
            try:
                tag, created = Tag.objects.get_or_create(name=tag_name)
                if created:
                    tag.slug = tag_name.lower().replace(' ', '-')
                    tag.save()
                tags.append(tag)
                if created:
                    self.stdout.write(f'  Created tag: {tag_name}')
            except Exception:
                tag = Tag.objects.filter(name=tag_name).first()
                if tag:
                    tags.append(tag)
        
        # Create an Organization
        org, created = Organization.objects.get_or_create(
            name='Acme Corporation',
            defaults={
                'slug': 'acme-corp',
                'is_active': True,
            }
        )
        if created:
            self.stdout.write(f'  Created organization: {org.name}')
        
        # Create Instructors
        instructor_data = [
            ('Michael', 'Rodriguez', 'michael@example.com'),
            ('Emma', 'Chen', 'emma@example.com'),
            ('David', 'Wilson', 'david@example.com'),
            ('Sarah', 'Kim', 'sarah@example.com'),
        ]
        
        instructors = []
        for first, last, email in instructor_data:
            try:
                user, created = User.objects.get_or_create(
                    email=email,
                    defaults={
                        'first_name': first,
                        'last_name': last,
                        'username': email.split('@')[0],
                        'role': User.Role.INSTRUCTOR,
                        'is_active': True,
                    }
                )
                instructors.append(user)
                if created:
                    self.stdout.write(f'  Created instructor: {first} {last}')
            except Exception:
                user = User.objects.filter(email=email).first()
                if user:
                    instructors.append(user)
        
        # Create Courses (10 courses)
        courses_data = [
            ('Advanced React Patterns & Best Practices', 'advanced-react-patterns', categories[0], instructors[0], 'Advanced', 24, 199.99, 'Master advanced React patterns, hooks, and performance optimization techniques.'),
            ('Data Science & Machine Learning Fundamentals', 'data-science-ml-fundamentals', categories[1], instructors[1], 'Beginner', 36, 149.99, 'Learn data science and machine learning from scratch with Python.'),
            ('Cybersecurity Essentials: From Zero to Hero', 'cybersecurity-essentials', categories[2], instructors[2], 'Intermediate', 28, 179.99, 'Complete cybersecurity bootcamp covering ethical hacking and penetration testing.'),
            ('Complete Product Management Bootcamp', 'product-management-bootcamp', categories[3], instructors[3], 'Intermediate', 32, 129.99, 'Learn product management skills from idea to launch.'),
            ('UX Design Masterclass', 'ux-design-masterclass', categories[4], instructors[0], 'Beginner', 18, 99.99, 'Master UX design with Figma and learn user research methodologies.'),
            ('Digital Marketing Strategy Complete Guide', 'digital-marketing-strategy', categories[5], instructors[1], 'Beginner', 22, 89.99, 'Learn SEO, social media marketing, and content strategy.'),
            ('Node.js API Development', 'nodejs-api-development', categories[0], instructors[2], 'Intermediate', 20, 159.99, 'Build scalable APIs with Node.js, Express, and MongoDB.'),
            ('Deep Learning with TensorFlow & PyTorch', 'deep-learning-tensorflow-pytorch', categories[1], instructors[3], 'Advanced', 42, 249.99, 'Master deep learning with TensorFlow and PyTorch frameworks.'),
            ('Ethical Hacking & Penetration Testing', 'ethical-hacking-pentesting', categories[2], instructors[0], 'Advanced', 35, 199.99, 'Learn ethical hacking and penetration testing methodologies.'),
            ('Cloud Architecture with AWS', 'cloud-architecture-aws', categories[6], instructors[1], 'Intermediate', 30, 189.99, 'Design and deploy scalable cloud solutions with AWS.'),
        ]
        
        for title, slug, category, instructor, level, hours, price, desc in courses_data:
            course, created = Course.objects.get_or_create(
                slug=slug,
                defaults={
                    'title': title,
                    'category': category,
                    'instructor': instructor,
                    'level': level,
                    'duration_hours': hours,
                    'price': Decimal(str(price)),
                    'description': desc,
                    'short_description': desc[:150],
                    'status': Course.Status.PUBLISHED,
                    'featured': courses_data.index((title, slug, category, instructor, level, hours, price, desc)) < 3,
                }
            )
            if created:
                course.tags.set(tags[:4])
                self.stdout.write(f'  Created course: {title}')
        
        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
