# PawPal+ (Module 2 Project)


## What My Project Originally Did
My PawPal+ project originally served as a scheduling application that allowed users to add their pets and then add tasks relating to their pets into the scheduler. They could input any task they needed, its duration, its priority rating (and whether it was required), and the time of day the task was to be completed. After adding all their tasks, depending on their inputted available time, the program would generate a schedule for the user that prioritizes required tasks and high priority tasks while staying within the user's time availability. The program would also notify the user of any schedule conflicts so that the user could go and modify their tasks to fix the issues. 

## Title and Summary
I modified my PawPal+ project to include a chatbot that could assist the user with any questions regarding the schedule that was generated, and could also suggest and (upon user approval) implement changes that would allow the schedule to better suit the user's needs. This includes recognizing schedule conflicts and automatically generating meaningful suggestions that the user is just one click away from viewing and approving. 

## Architecture Overview
My system diagram consists of 5 classes, the Owner, Pet, Task, Scheduler, and SchedulingAgent. The Owner owns Pets and Tasks, with the ability to add Pets and contain/filter tasks. The Pet contains its own list of Tasks that are related to it and have multiple attributes involving their characteristics. Tasks can be added and removed for pets as well as marked complete. The Scheduler maintains the Tasks, scheduled Tasks, Unscheduled Tasks, conflicts, reasonings, and available minutes of the Owner. Lastly the Scheduling Agent is able to read from the Scheduler and Owner to plan queries and responses for suggestions/answers. 

## Setup Instructions
1. git clone https://github.com/humanchild101/PawPal-Applied-AI-System-Project-.git
2. code . 
3. Go to https://console.groq.com/keys and login
4. Create an API key and copy the key. 
5. Create a file called secrets.toml in the .streamlit folder. There should be another file called secrets.toml.example. Copy everything from that into the secrets.toml file and paste the API key in. 
6. Run streamlit run app.py

## Sample Interactions
|Inputs|Output|
|------|------|
|Why is calming Pu's tantrum not scheduled|The task "Calm Pu Tantrum" is not scheduled because it has a lower priority (4) compared to other tasks in the plan. The available time for the day is 300 minutes, and most of the tasks have higher priorities and are already scheduled, leaving only 10 minutes of remaining time. The task "Calm Pu Tantrum" requires 15 minutes, which is more than the remaining time available.

Additionally, there is a conflict between "Bathe Pu" and "PuPi Playdate" as they are both scheduled for the same time (11:00 AM).

To accommodate "Calm Pu Tantrum", you could consider adjusting the schedule of other tasks or proposing a change to the available time for the day. Would you like me to propose a change?|
|Please suggest a way to resolve the conflicts in the schedule.|I unfortunately cannot paste the exact response here because the response disappeared after I clicked 'accept' to its suggestion. Groq has a daily limit and I have used all of the tokens, so I cannot prompt it again. The suggestion it gave was along the lines of changing my available time limit to a higher number and then change the time of day of one of the tasks that was overlapping with other task and creating a conflict.|

## Design Decisions
I built the applied AI system, implementing agentic workflow and RAG. The system itself is essentially a chatbot but it can also suggest and act (upon user approval). Data is retrevied from the Scheduler and Owner for specific information to answer the user's question with specific context instead of general information. The agentic workflow ensures that the user does not have to manually look through the gaps in the schedule/determine where conflicts are occuring and make decisions to fix them. The agent takes care of analyzing the conflicts and suggesting/implementing solutions approved by the user. One tradeoff I had to make (which has more to do with the API than the AI functionality itself) was that I could not use Gemini's API because it kept preventing me from doing so by redirecting me to a certain page. I did a lot of research but the suggested reasons for the issue were not applicable to me. I ended up using Groq's API, which works well, but it has a rate limit which has proved to be an inconvenience during testing because it would make me wait some time before testing again. I did not have too many options to work with. A more relavent tradeoff was that in return for scheduling that prioritizes required tasks and the user's time availability, a more 'sophisticated' AI that could provide more flexible suggestions on what should and should not be scheduled was not implemented. 
 

## Testing Summary
During the process of designing the AI system, there were many things that didn't work right and many that did. One positive was that instead of having just a simple chatbot that answered questions based on retreival of context, the chatbot worked with an agentic workflow which gave it more functionality and purpose in the program. One thing I think was very convenient during testing was preloading the application with testing data to use/modify while testing by adding a section at the top that would implplement this with a button click. One issue that occured was that the formatting of the AI responses was not easily readable (). As well as this, the AI would format its answers directly referencing variables and functions from the code. One other issue that surfaced when testing was that the AI did not directly make the changes it was approved to make. The values it was supposed to change would remain the same and I had to go and manually change them to see if the AI's change actually worked. I also had several issues with the API during testing where it would simply not work or would make me wait x amount of time before the next prompt (as mentioned earlier in this document.) These issues were all ultimately resolved though, and while the AI is not perfect right now, it works as intended for this small program. I learned a lot about implementing AI systems into projects. I chose to work with Groq's API and in the process of figure out that issue, I learned about the different available options. I also learned about the limitations of Groq and others, and it has led me to look into other options I could use in the future. I learned about RAG and agentic systems more through the direct implementation of them in my project. The project also made me think about how I could implement ideas next time which users could also easily access without going through the steps of manually installing APIs on their end. 