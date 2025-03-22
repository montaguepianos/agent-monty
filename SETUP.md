**Monty Deployment & Update Guide (Render + GitHub + Flask)**

Last updated: March 2025

---

### 🔧 Purpose
This is your step-by-step cheat sheet for updating either the **backend** (Flask) or **frontend** (HTML/JS) for your chatbot "Monty" hosted on Render and version-controlled with GitHub.

---

### ✅ BEFORE YOU START
Make sure you're on your Mac and in the project folder (`agent-monty`). If you're not sure where you left off, look for `app.py`, `requirements.txt`, or your virtual environment folder.

---

### ① Open the Project and Activate the Virtual Environment

```bash
# Right-click the agent-monty folder > Open Terminal at Folder
source agent-monty-env/bin/activate
```

You'll know it's active when your prompt shows:
```bash
(agent-monty-env) (base) leechapman@Mac...
```

---

### ② Make Your Changes

- **Backend (Flask)**: Edit `app.py`, add routes, logic, OpenAI API calls, etc.
- **Frontend (HTML/JS)**: Edit your `templates/` or `static/` folders
- **Dependencies?** If you install a new package:

```bash
pip install something
pip freeze > requirements.txt
```

---

### ③ Stage, Commit & Push to GitHub

```bash
git add .
git commit -m "changed the frontend added thinking sounds"
git push
```

This automatically triggers a redeploy on Render (usually within ~60 seconds).

If it's the first push from a new machine or setup:
```bash
git push --set-upstream origin main
```

> ⚠️ If you get authentication errors, use your GitHub **personal access token** as the password.

---

### ④ Monitor the Deployment on Render

1. Go to [https://dashboard.render.com](https://dashboard.render.com)
2. Click on `agent-monty`
3. Click **Events** tab

Look for:
```
Deploy started...
Deploy live for <commit message>
```

> Use the **Logs** tab if something fails (e.g. missing package, import error)

---

### ✅ Monty is Live!
Visit:
```
https://agent-monty.onrender.com
```

You can embed or share this link anywhere (WordPress iframe, etc.)

---

### ♻ Optional Cleanup (for later)
If `agent-monty-env/` or other big folders got committed:
```bash
echo agent-monty-env/ >> .gitignore
git rm -r --cached agent-monty-env
git commit -m "Clean: removed venv from repo"
git push
```

---

### 🎧 Future Improvements
- Add secret keys via Render's environment variable panel
- Auto-scroll chat UI / save sessions
- Make widget version for WordPress popup

---

Nice work, future Lee. You deployed Monty like a boss.
If anything breaks, just message ChatGPT 4o... not O1. O1 stinks.

