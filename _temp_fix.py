import os

file_path = 'apps/catalogue/views.py'
with open(file_path, 'r', encoding='utf-8') as f:
    orig_text = f.read()

old_str = """if request.method == "GET":
    quiz = self._get_or_create_quiz(session)
    return Response(self._build_quiz_detail_response(session, quiz, request))

    if request.method == "POST":
        if Quiz.objects.filter(session=session).exists():
            return Response(
                {"detail": "Quiz already exists for this session."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        quiz = Quiz.objects.create(
            session=session, settings=request.data.get("settings", {})
        )
return Response(
    self._build_quiz_detail_response(session, quiz, request),
    status=status.HTTP_201_CREATED,
)

    else:  # PATCH"""

new_str = """        if request.method == "GET":
            quiz = self._get_or_create_quiz(session)
            return Response(self._build_quiz_detail_response(session, quiz, request))

        elif request.method == "POST":
            if Quiz.objects.filter(session=session).exists():
                return Response(
                    {"detail": "Quiz already exists for this session."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            quiz = Quiz.objects.create(
                session=session, settings=request.data.get("settings", {})
            )
            return Response(
                self._build_quiz_detail_response(session, quiz, request),
                status=status.HTTP_201_CREATED,
            )

        else:  # PATCH"""

out_text = orig_text.replace(old_str, new_str).replace(old_str.replace('\n', '\r\n'), new_str)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(out_text)
