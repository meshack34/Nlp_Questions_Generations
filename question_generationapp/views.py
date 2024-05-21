
from django.shortcuts import render
from questiongenerator import QuestionGenerator
from training import qa_eval_train
from training.dataset import QAEvalDataset

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseBadRequest
from django.contrib import messages
from datetime import date
from .forms import *
from .models import ( User,
    Account,
)
from django.contrib import messages, auth
import datetime
from re import split
from django.http import FileResponse
import io
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from questiongenerator import QuestionGenerator

def home(request):
    card_list = Card.objects.all()  
    context = {
        'card_list': card_list
    }

    return render(request, 'home.html', context)




def userregister(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            if Account.objects.filter(email=email).exists():
                messages.error(request, 'Email is already registered.')
                return redirect('userregister')
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            phone_number = form.cleaned_data['phone_number']
            password = form.cleaned_data['password']
            username = email.split("@")[0]
            user = Account.objects.create_user(first_name=first_name, last_name=last_name, email=email, username=username, password=password)
            user.user_type = 'User'  # Set user type to 'User'
            user.phone_number = phone_number
            user.save()

            messages.success(request, 'Registration successful. You can now login.')
            return redirect('login')
    else:
        form = RegistrationForm()
    
    context = {
        'form': form
    }
    return render(request, 'users/register.html', context)




def login(request):
    if request.method == 'POST':
        email = request.POST['email']
        password = request.POST['password']

        user = auth.authenticate(email=email, password=password)

        if user is not None:
            auth.login(request, user)
            return redirect('generate_question')  # Redirect to a common dashboard for all users
        else:
            messages.error(request, 'Invalid email or password.')
            return redirect('login')

    return render(request, 'users/login.html')





@login_required(login_url='login')
def logout(request):
    auth.logout(request)
    messages.success(request, 'You are logged out.')
    return redirect('home')

def dashboard(request):
    if request.user.is_authenticated:
        current_user = request.user
        context = {
            'user': current_user,
        }
        return render(request,'users/user_dashboard.html', context)
    else:
       
        pass


def generate_questions(request):
    if request.method == 'POST':
        text_content = request.POST.get('text_content', '')
        qg = QuestionGenerator()
        qa_list = qg.generate(
            text_content,
            num_questions=10,
            answer_style='all',
            use_evaluator=True
        )
        # Separate questions based on their type
        questions_with_answers = [qa for qa in qa_list if 'answer' in qa]
        open_ended_questions = [qa for qa in qa_list if 'answer' not in qa]
        context = {
            'text_content': text_content,
            'questions_with_answers': questions_with_answers,
            'open_ended_questions': open_ended_questions,
        }
    else:
        context = {}
    
    return render(request, 'users/user_dashboard.html', context)


